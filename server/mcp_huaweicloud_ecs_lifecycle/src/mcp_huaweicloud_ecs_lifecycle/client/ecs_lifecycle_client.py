# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Thin SDK wrapper for ECS lifecycle plus read-only IMS/VPC discovery calls.

No business logic here: every method maps one API call to plain JSON data.
"""

from __future__ import annotations

import os
from typing import Any

from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.credentials import CredentialScope, build_credentials

from huaweicloud_mcp_ecs_common import call_sdk, paginate, sdk_to_dict


class EcsLifecycleClient:
    """Async wrapper around the synchronous Huawei Cloud SDK clients.

    The primary service is ECS; IMS (images) and VPC (subnets) are secondary
    clients built lazily from the same credentials. Endpoint derivation: an
    explicit ``ecs.*`` host swaps its first DNS label per service; any other
    explicit host (gateway style) is reused verbatim; without an endpoint each
    service synthesizes ``https://<service>.<region>.myhuaweicloud.com``.
    """

    MAX_PAGE_SIZE = 1000
    _IMAGE_PAGE_SIZE = 100
    _MAX_IMAGE_PAGES = 30
    _MAX_FLAVOR_PAGES = 10
    _MAX_SUBNET_PAGES = 10

    def __init__(
        self,
        settings: McpSettings | None = None,
        sdk_client: Any = None,
    ) -> None:
        self._settings = settings or McpSettings.from_env()
        self._sdk_client = sdk_client
        self._service_clients: dict[str, Any] = {}
        endpoint = self._settings.endpoint
        if endpoint and not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"
        self._endpoint = endpoint
        # Internal test regions (e.g. cn-southwest-242) present a self-signed
        # certificate over the VPN tunnel. Only skip TLS validation when the
        # operator explicitly lists this region; off by default and never applied
        # to unlisted regions, so public regions stay strictly verified. Applies
        # to every service client (ecs/ims/vpc) built below.
        self._skip_ssl_verify_regions = {
            r.strip()
            for r in os.getenv("HUAWEICLOUD_MCP_SKIP_SSL_VERIFY_REGIONS", "").split(",")
            if r.strip()
        }
        if sdk_client is not None:
            # Test seam: every service routes to the injected stub, so no real
            # SDK client (and no IAM round trip for credentials) is constructed.
            self._credentials = None
        else:
            # Built once: resolving the project id can hit IAM, and building a
            # client per service must not repeat that round trip.
            self._credentials = build_credentials(CredentialScope.PROJECT, self._settings)
        self._client = self._service_client("ecs")

    def _service_client(self, service: str) -> Any:
        if self._sdk_client is not None:
            return self._sdk_client
        if service not in self._service_clients:
            self._service_clients[service] = self._build_service_client(service)
        return self._service_clients[service]

    def _build_service_client(self, service: str) -> Any:
        from huaweicloudsdkcore.region.region import Region

        if service == "ecs":
            from huaweicloudsdkecs.v2 import EcsClient as client_cls
            from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion as region_cls
        elif service == "ims":
            from huaweicloudsdkims.v2 import ImsClient as client_cls
            from huaweicloudsdkims.v2.region.ims_region import ImsRegion as region_cls
        elif service == "vpc":
            from huaweicloudsdkvpc.v2 import VpcClient as client_cls
            from huaweicloudsdkvpc.v2.region.vpc_region import VpcRegion as region_cls
        else:
            raise ValueError(f"Unsupported service: {service}")

        region_id = self._settings.region
        if self._endpoint:
            # Explicit endpoint override wins over the SDK's static region map.
            sdk_region = Region(region_id, self._service_endpoint(service))
        else:
            try:
                sdk_region = region_cls.value_of(region_id)
            except KeyError:
                # Internal/beta regions are absent from the SDK's static map; every
                # map entry follows https://<service>.<region>.myhuaweicloud.com, so
                # synthesize on that pattern instead of failing at construction.
                sdk_region = Region(region_id, self._service_endpoint(service))
        from huaweicloudsdkcore.http.http_config import HttpConfig

        http_config = HttpConfig.get_default_config()
        if region_id in self._skip_ssl_verify_regions:
            http_config.ignore_ssl_verification = True
        return (
            client_cls.new_builder()
            .with_credentials(self._credentials)
            .with_region(sdk_region)
            .with_http_config(http_config)
            .build()
        )

    def _service_endpoint(self, service: str) -> str:
        """Derive one service's endpoint from the configured endpoint."""
        if not self._endpoint:
            return f"https://{service}.{self._settings.region}.myhuaweicloud.com"
        scheme, _, host = self._endpoint.partition("//")
        first, _, rest = host.partition(".")
        if first == "ecs" and rest:
            return f"{scheme}//{service}.{rest}"
        # Gateway-style override: all services share the same host.
        return self._endpoint

    # ------------------------------------------------------------------ servers

    async def list_all_servers(self) -> list[dict[str, Any]]:
        """Fetch every server in the region by paging through list-servers-details."""

        def _call() -> list[dict[str, Any]]:
            from huaweicloudsdkecs.v2.model.list_servers_details_request import (
                ListServersDetailsRequest,
            )

            offset = 1

            def fetch() -> Any:
                nonlocal offset
                request = ListServersDetailsRequest(limit=self.MAX_PAGE_SIZE, offset=offset)
                # Let SDK/transport exceptions surface raw to call_sdk so its retry
                # layer sees ServiceResponseException(429/5xx) and transport blips —
                # wrap_sdk_error in the client would pre-wrap them as McpToolError
                # and defeat the retry (it only re-wraps at the call_sdk boundary).
                response = self._client.list_servers_details(request)
                return response

            def advance(_batch: list[dict[str, Any]], _page: dict[str, Any]) -> str | None:
                nonlocal offset
                offset += 1
                # offset-style paging: return the next offset as the sentinel so the
                # dedupe guard sees a fresh value each page; the loop stops on an
                # empty/short page in paginate itself.
                return str(offset)

            return paginate(
                fetch,
                result_key="servers",
                page_size=self.MAX_PAGE_SIZE,
                advance=advance,
            )

        return await call_sdk(_call)

    async def show_server(self, server_id: str) -> dict[str, Any]:
        """Fetch a single server detail."""

        def _call() -> dict[str, Any]:
            from huaweicloudsdkecs.v2.model.show_server_request import ShowServerRequest

            request = ShowServerRequest(server_id=server_id)
            # Let SDK/transport exceptions surface raw to call_sdk (see list_all_servers).
            response = self._client.show_server(request)
            return sdk_to_dict(response) or {}

        return await call_sdk(_call)

    # ---------------------------------------------------------------- discovery

    async def list_images(self) -> list[dict[str, Any]]:
        """Fetch all images (public + private) by paging the IMS list-images API.

        Unlike list_flavors/list_subnets (which page via the shared ``paginate``
        helper, where each page is its own ``call_sdk`` and its own semaphore
        slot), this method's ``_call`` does the whole paging loop inside one
        ``call_sdk`` — so one ``list_images`` call holds a single slot for all
        its pages, not one per page. That is fine in practice (the catalog is a
        few pages), but it means ``MAX_CONCURRENT`` bounds *tool calls* here,
        not *API requests*; a small cap with a large catalog could serialize
        this call behind fewer concurrent tool calls than the cap suggests.
        """

        def _call() -> list[dict[str, Any]]:
            from huaweicloudsdkims.v2.model.list_images_request import ListImagesRequest

            images: list[dict[str, Any]] = []
            marker: str | None = None
            for _ in range(self._MAX_IMAGE_PAGES):
                request = ListImagesRequest(limit=self._IMAGE_PAGE_SIZE)
                if marker:
                    request.marker = marker
                # Let SDK/transport exceptions surface raw to call_sdk (see list_all_servers).
                response = self._service_client("ims").list_images(request)
                page = sdk_to_dict(response) or {}
                batch = page.get("images") or []
                images.extend(batch)
                marker = (page.get("page_info") or {}).get("next_marker")
                if not batch or not marker:
                    break
            return images

        return await call_sdk(_call)

    async def list_flavors(self, flavor_id: str | None = None) -> list[dict[str, Any]]:
        """Fetch the flavor catalog paging by marker; flavor_id does an exact lookup.

        The API caps one page at 1000 flavors, so a large catalog loses its
        alphabetical tail unless paged — the tail is where flavors like
        ``x1.*`` live, which existing servers may still use.
        """

        def _call() -> list[dict[str, Any]]:
            from huaweicloudsdkecs.v2.model.list_flavors_request import ListFlavorsRequest

            marker: str | None = None

            def fetch() -> Any:
                nonlocal marker
                request = ListFlavorsRequest(limit=self.MAX_PAGE_SIZE)
                if flavor_id:
                    request.flavor_id = flavor_id
                if marker:
                    request.marker = marker
                # Let SDK/transport exceptions surface raw to call_sdk (see list_all_servers).
                response = self._client.list_flavors(request)
                return response

            def advance(batch: list[dict[str, Any]], _page: dict[str, Any]) -> str | None:
                # ECS list-flavors pages by the last item's id (no page_info.next_marker);
                # the next fetch() reads this via the nonlocal marker.
                nonlocal marker
                marker = str(batch[-1].get("id") or "")
                return marker or None

            return paginate(
                fetch,
                result_key="flavors",
                page_size=self.MAX_PAGE_SIZE,
                max_pages=self._MAX_FLAVOR_PAGES,
                advance=advance,
            )

        return await call_sdk(_call)

    async def list_keypairs(self) -> list[dict[str, Any]]:
        """List SSH key pairs via the Nova keypairs API.

        nova_list_keypairs is deprecated upstream but remains the only list
        endpoint the SDK exposes; the nested [{keypair: {...}}] shape is kept
        for the service layer to flatten.
        """

        def _call() -> list[dict[str, Any]]:
            from huaweicloudsdkecs.v2.model.nova_list_keypairs_request import (
                NovaListKeypairsRequest,
            )

            request = NovaListKeypairsRequest()
            # Let SDK/transport exceptions surface raw to call_sdk (see list_all_servers).
            response = self._client.nova_list_keypairs(request)
            page = sdk_to_dict(response) or {}
            return page.get("keypairs") or []

        return await call_sdk(_call)

    async def list_subnets(self) -> list[dict[str, Any]]:
        """Fetch all subnets in the region (internal default-resolution helper)."""

        def _call() -> list[dict[str, Any]]:
            from huaweicloudsdkvpc.v2.model.list_subnets_request import ListSubnetsRequest

            marker: str | None = None

            def fetch() -> Any:
                nonlocal marker
                request = ListSubnetsRequest(limit=self.MAX_PAGE_SIZE)
                if marker:
                    request.marker = marker
                # Let SDK/transport exceptions surface raw to call_sdk (see list_all_servers).
                response = self._service_client("vpc").list_subnets(request)
                return response

            def advance(batch: list[dict[str, Any]], _page: dict[str, Any]) -> str | None:
                # VPC list-subnets pages by the last item's id (no page_info.next_marker);
                # the next fetch() reads this via the nonlocal marker.
                nonlocal marker
                marker = str(batch[-1].get("id") or "")
                return marker or None

            return paginate(
                fetch,
                result_key="subnets",
                page_size=self.MAX_PAGE_SIZE,
                max_pages=self._MAX_SUBNET_PAGES,
                advance=advance,
            )

        return await call_sdk(_call)

    # ------------------------------------------------------------- changing ops

    async def create_pre_paid_server(
        self,
        *,
        name: str,
        flavor_ref: str,
        image_ref: str,
        vpc_id: str,
        subnet_id: str,
        root_volume_type: str,
        root_volume_size: int | None = None,
        admin_pass: str | None = None,
        key_name: str | None = None,
        count: int = 1,
        availability_zone: str | None = None,
        description: str | None = None,
        user_data: str | None = None,
        security_group_id: str | None = None,
        eip_bandwidth: int | None = None,
        period_type: str = "month",
        period_num: int = 1,
        is_auto_pay: bool = False,
        is_auto_renew: bool = False,
        is_auto_rename: bool = False,
    ) -> dict[str, Any]:
        """Create prepaid (monthly/yearly) servers; returns the async job."""

        def _call() -> dict[str, Any]:
            from huaweicloudsdkecs.v2.model.create_servers_request import CreateServersRequest
            from huaweicloudsdkecs.v2.model.create_servers_request_body import (
                CreateServersRequestBody,
            )
            from huaweicloudsdkecs.v2.model.pre_paid_server import PrePaidServer
            from huaweicloudsdkecs.v2.model.pre_paid_server_eip import PrePaidServerEip
            from huaweicloudsdkecs.v2.model.pre_paid_server_eip_bandwidth import (
                PrePaidServerEipBandwidth,
            )
            from huaweicloudsdkecs.v2.model.pre_paid_server_extend_param import (
                PrePaidServerExtendParam,
            )
            from huaweicloudsdkecs.v2.model.pre_paid_server_nic import PrePaidServerNic
            from huaweicloudsdkecs.v2.model.pre_paid_server_publicip import (
                PrePaidServerPublicip,
            )
            from huaweicloudsdkecs.v2.model.pre_paid_server_root_volume import (
                PrePaidServerRootVolume,
            )
            from huaweicloudsdkecs.v2.model.pre_paid_server_security_group import (
                PrePaidServerSecurityGroup,
            )

            kwargs: dict[str, Any] = {}
            if security_group_id:
                kwargs["security_groups"] = [PrePaidServerSecurityGroup(id=security_group_id)]
            if eip_bandwidth:
                # delete_on_termination releases the EIP with the server, so a
                # deleted instance never leaves an orphaned (still billed) IP.
                kwargs["publicip"] = PrePaidServerPublicip(
                    eip=PrePaidServerEip(
                        iptype="5_bgp",
                        bandwidth=PrePaidServerEipBandwidth(
                            size=eip_bandwidth, sharetype="PER", chargemode="traffic"
                        ),
                    ),
                    delete_on_termination=True,
                )
            server = PrePaidServer(
                name=name,
                flavor_ref=flavor_ref,
                image_ref=image_ref,
                vpcid=vpc_id,
                nics=[PrePaidServerNic(subnet_id=subnet_id)],
                root_volume=PrePaidServerRootVolume(
                    volumetype=root_volume_type, size=root_volume_size
                ),
                admin_pass=admin_pass,
                key_name=key_name,
                count=count,
                availability_zone=availability_zone,
                description=description,
                user_data=user_data,
                is_auto_rename=is_auto_rename,
                extendparam=PrePaidServerExtendParam(
                    charging_mode="prePaid",
                    period_type=period_type,
                    period_num=period_num,
                    # The API expects "true"/"false" strings here, not booleans.
                    is_auto_pay="true" if is_auto_pay else "false",
                    is_auto_renew="true" if is_auto_renew else "false",
                ),
                **kwargs,
            )
            request = CreateServersRequest(body=CreateServersRequestBody(server=server))
            # Let SDK/transport exceptions surface raw to call_sdk (see list_all_servers).
            response = self._client.create_servers(request)
            return sdk_to_dict(response) or {}

        return await call_sdk(_call)

    async def create_post_paid_server(
        self,
        *,
        name: str,
        flavor_ref: str,
        image_ref: str,
        vpc_id: str,
        subnet_id: str,
        root_volume_type: str,
        root_volume_size: int | None = None,
        admin_pass: str | None = None,
        key_name: str | None = None,
        count: int = 1,
        availability_zone: str | None = None,
        description: str | None = None,
        user_data: str | None = None,
        security_group_id: str | None = None,
        eip_bandwidth: int | None = None,
        is_auto_rename: bool = False,
    ) -> dict[str, Any]:
        """Create post-paid (pay-per-use) servers; returns the async job."""

        def _call() -> dict[str, Any]:
            from huaweicloudsdkecs.v2.model.create_post_paid_servers_request import (
                CreatePostPaidServersRequest,
            )
            from huaweicloudsdkecs.v2.model.create_post_paid_servers_request_body import (
                CreatePostPaidServersRequestBody,
            )
            from huaweicloudsdkecs.v2.model.post_paid_server import PostPaidServer
            from huaweicloudsdkecs.v2.model.post_paid_server_eip import PostPaidServerEip
            from huaweicloudsdkecs.v2.model.post_paid_server_eip_bandwidth import (
                PostPaidServerEipBandwidth,
            )
            from huaweicloudsdkecs.v2.model.post_paid_server_extend_param import (
                PostPaidServerExtendParam,
            )
            from huaweicloudsdkecs.v2.model.post_paid_server_nic import PostPaidServerNic
            from huaweicloudsdkecs.v2.model.post_paid_server_publicip import (
                PostPaidServerPublicip,
            )
            from huaweicloudsdkecs.v2.model.post_paid_server_root_volume import (
                PostPaidServerRootVolume,
            )
            from huaweicloudsdkecs.v2.model.post_paid_server_security_group import (
                PostPaidServerSecurityGroup,
            )

            kwargs: dict[str, Any] = {}
            if security_group_id:
                kwargs["security_groups"] = [PostPaidServerSecurityGroup(id=security_group_id)]
            if eip_bandwidth:
                # delete_on_termination releases the EIP with the server, so a
                # deleted instance never leaves an orphaned (still billed) IP.
                kwargs["publicip"] = PostPaidServerPublicip(
                    eip=PostPaidServerEip(
                        iptype="5_bgp",
                        bandwidth=PostPaidServerEipBandwidth(
                            size=eip_bandwidth, sharetype="PER", chargemode="traffic"
                        ),
                    ),
                    delete_on_termination=True,
                )
            server = PostPaidServer(
                name=name,
                flavor_ref=flavor_ref,
                image_ref=image_ref,
                vpcid=vpc_id,
                nics=[PostPaidServerNic(subnet_id=subnet_id)],
                root_volume=PostPaidServerRootVolume(
                    volumetype=root_volume_type, size=root_volume_size
                ),
                admin_pass=admin_pass,
                key_name=key_name,
                count=count,
                availability_zone=availability_zone,
                description=description,
                user_data=user_data,
                is_auto_rename=is_auto_rename,
                # extendparam is required for post-paid; charging_mode 0 = pay-per-use.
                extendparam=PostPaidServerExtendParam(charging_mode=0),
                **kwargs,
            )
            request = CreatePostPaidServersRequest(
                body=CreatePostPaidServersRequestBody(server=server)
            )
            # Let SDK/transport exceptions surface raw to call_sdk (see list_all_servers).
            response = self._client.create_post_paid_servers(request)
            return sdk_to_dict(response) or {}

        return await call_sdk(_call)

    async def update_server(
        self,
        *,
        server_id: str,
        name: str | None = None,
        description: str | None = None,
        hostname: str | None = None,
    ) -> dict[str, Any]:
        """Rename / re-describe a server; omitted fields stay unchanged."""

        def _call() -> dict[str, Any]:
            from huaweicloudsdkecs.v2.model.update_server_option import UpdateServerOption
            from huaweicloudsdkecs.v2.model.update_server_request import UpdateServerRequest
            from huaweicloudsdkecs.v2.model.update_server_request_body import (
                UpdateServerRequestBody,
            )

            request = UpdateServerRequest(
                server_id=server_id,
                body=UpdateServerRequestBody(
                    server=UpdateServerOption(name=name, description=description, hostname=hostname)
                ),
            )
            # Let SDK/transport exceptions surface raw to call_sdk (see list_all_servers).
            response = self._client.update_server(request)
            return sdk_to_dict(response) or {}

        return await call_sdk(_call)

    async def delete_servers(
        self,
        *,
        server_ids: list[str],
        delete_volume: bool = False,
        delete_publicip: bool = False,
    ) -> dict[str, Any]:
        """Delete servers asynchronously; returns the async job."""

        def _call() -> dict[str, Any]:
            from huaweicloudsdkecs.v2.model.delete_servers_request import DeleteServersRequest
            from huaweicloudsdkecs.v2.model.delete_servers_request_body import (
                DeleteServersRequestBody,
            )
            from huaweicloudsdkecs.v2.model.server_id import ServerId

            request = DeleteServersRequest(
                body=DeleteServersRequestBody(
                    delete_publicip=delete_publicip,
                    delete_volume=delete_volume,
                    servers=[ServerId(id=sid) for sid in server_ids],
                )
            )
            # Let SDK/transport exceptions surface raw to call_sdk (see list_all_servers).
            response = self._client.delete_servers(request)
            return sdk_to_dict(response) or {}

        return await call_sdk(_call)

    async def show_job(self, job_id: str) -> dict[str, Any]:
        """Fetch the status of an async job (create/delete)."""

        def _call() -> dict[str, Any]:
            from huaweicloudsdkecs.v2.model.show_job_request import ShowJobRequest

            request = ShowJobRequest(job_id=job_id)
            # Let SDK/transport exceptions surface raw to call_sdk (see list_all_servers).
            response = self._client.show_job(request)
            return sdk_to_dict(response) or {}

        return await call_sdk(_call)
