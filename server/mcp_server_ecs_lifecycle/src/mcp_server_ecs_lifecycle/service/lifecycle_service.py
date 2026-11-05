# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Service layer: ECS lifecycle scenarios (create/update/delete + discovery views).

Every mutating scenario follows the two-branch confirm protocol: with confirm=False
it returns a preview and performs no side effect; with confirm=True it re-checks
protection rules against real cloud attributes before executing. Creation follows
an intent-driven design: core parameters only, server-side smart defaults for the
rest, and the preview always shows the exact configuration that would be executed.
"""

from __future__ import annotations

import base64
from typing import Any

from huaweicloud_mcp_core.errors import McpToolError
from huaweicloud_mcp_core.guardrails import assert_not_protected
from huaweicloud_mcp_core.output import clamp_limit, page_result, single_result

from mcp_server_ecs_lifecycle.client.ecs_lifecycle_client import EcsLifecycleClient

_LIST_FIELDS = (
    "id",
    "name",
    "status",
    "flavor",
    "addresses",
    "tags",
    "created",
)

_SHOW_FIELDS = (
    "id",
    "name",
    "status",
    "description",
    "flavor",
    "image",
    "addresses",
    "security_groups",
    "key_name",
    "created",
    "updated",
    "tags",
)

_IMAGE_FIELDS = (
    "id",
    "name",
    "os_type",
    "os_version",
    "status",
    "imagetype",
    "min_disk",
    "min_ram",
    "visibility",
)

_FLAVOR_FIELDS = ("id", "name", "vcpus", "ram", "disk")

_KEYPAIR_FIELDS = ("name", "fingerprint", "type")

# The SDK exposes the availability zone under this legacy OpenStack-style key.
_ZONE_KEY = "os_ext_a_zavailability_zone"

_JOB_FIELDS = (
    "job_id",
    "status",
    "error_code",
    "fail_reason",
    "job_type",
    "entities",
    "begin_time",
    "end_time",
)

_JOB_HINTS = {
    "INIT": "Job is queued; call show_job again later to check progress.",
    "RUNNING": "Job is still running; call show_job again later to check progress.",
}

_CONFIRM_SUFFIX = "Call again with confirm=true to proceed."

_MAX_BATCH_COUNT = 100
_MAX_USER_DATA_BYTES = 32 * 1024
_EIP_BANDWIDTH_RANGE = (1, 1000)
_DEFAULT_ROOT_VOLUME_TYPE = "SSD"


def _pick(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in fields if source.get(key) is not None}


def _encode_user_data(user_data: str | None) -> str | None:
    """Base64-encode a raw startup script; the API takes base64 and caps 32 KB."""
    if user_data is None:
        return None
    encoded = base64.b64encode(user_data.encode("utf-8")).decode("ascii")
    if len(encoded) > _MAX_USER_DATA_BYTES:
        raise McpToolError(
            "MCP_INVALID_ARGS",
            "user_data exceeds 32 KB after base64 encoding.",
            hint="Shorten the startup script or install heavyweight software manually.",
        )
    return encoded


class EcsLifecycleService:
    """Scenario orchestration for ECS lifecycle operations."""

    def __init__(self, client: EcsLifecycleClient | None = None) -> None:
        self._client = client or EcsLifecycleClient()

    # ------------------------------------------------------------------ read

    async def list_servers(
        self,
        *,
        name: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        servers = await self._fetch(name=name, status=status)
        items = [_pick(server, _LIST_FIELDS) for server in servers]
        total = len(items)
        limit = clamp_limit(limit)
        return page_result(items[:limit], total=total)

    async def show_server(self, server_id: str) -> dict[str, Any]:
        detail = await self._client.show_server(server_id)
        server = detail.get("server") or {}
        result = _pick(server, _SHOW_FIELDS)
        if _ZONE_KEY in server:
            result["availability_zone"] = server[_ZONE_KEY]
        return single_result(result)

    async def show_job(self, job_id: str) -> dict[str, Any]:
        job = await self._client.show_job(job_id)
        status = str(job.get("status") or "UNKNOWN")
        result = {"status": status, **_pick(job, _JOB_FIELDS)}
        if status in _JOB_HINTS:
            result["hint"] = _JOB_HINTS[status]
        return single_result(result)

    # ------------------------------------------------------------- discovery

    async def list_images(
        self,
        *,
        name: str | None = None,
        os_type: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Discover images (public + private) so the AI can pick an image_ref."""
        images = await self._client.list_images()
        if name:
            wanted = name.lower()
            images = [i for i in images if wanted in str(i.get("name") or "").lower()]
        if os_type:
            wanted = os_type.lower()
            images = [i for i in images if str(i.get("os_type") or "").lower() == wanted]
        items = [_pick(image, _IMAGE_FIELDS) for image in images]
        total = len(items)
        limit = clamp_limit(limit)
        return page_result(items[:limit], total=total)

    async def list_flavors(
        self,
        *,
        vcpus: int | None = None,
        ram_gb: int | None = None,
        flavor_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Discover flavors so the AI can pick a flavor_ref (vcpus exact, ram in GB)."""
        flavors = await self._client.list_flavors(flavor_id=flavor_id)
        if vcpus is not None:
            # The API returns vcpus as a string; compare stringly to be exact.
            flavors = [f for f in flavors if str(f.get("vcpus") or "") == str(vcpus)]
        if ram_gb is not None:
            flavors = [f for f in flavors if f.get("ram") == ram_gb * 1024]
        items = [_pick(flavor, _FLAVOR_FIELDS) for flavor in flavors]
        total = len(items)
        limit = clamp_limit(limit)
        return page_result(items[:limit], total=total)

    async def list_keypairs(self, *, limit: int = 20) -> dict[str, Any]:
        """List SSH key pairs so the AI can pick a key_name for login."""
        keypairs = await self._client.list_keypairs()
        items = []
        for entry in keypairs:
            # The Nova API nests each keypair under a "keypair" attribute.
            inner = entry.get("keypair")
            if not isinstance(inner, dict):
                inner = entry
            items.append(_pick(inner, _KEYPAIR_FIELDS))
        total = len(items)
        limit = clamp_limit(limit)
        return page_result(items[:limit], total=total)

    # -------------------------------------------------------------- changing

    async def create_server(
        self,
        *,
        name: str,
        flavor_ref: str,
        image_ref: str,
        vpc_id: str | None = None,
        subnet_id: str | None = None,
        root_volume_type: str | None = None,
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
        confirm: bool = False,
    ) -> dict[str, Any]:
        self._validate_create_args(
            count=count,
            admin_pass=admin_pass,
            key_name=key_name,
            period_type=period_type,
            period_num=period_num,
            eip_bandwidth=eip_bandwidth,
        )
        user_data = _encode_user_data(user_data)
        vpc_id, subnet_id, root_volume_type, defaults, subnet = await self._resolve_defaults(
            vpc_id, subnet_id, root_volume_type
        )
        preview: dict[str, Any] = {
            "operation": "create_server",
            "billing": "prePaid (monthly/yearly)",
            "name": name,
            "count": count,
            "flavor_ref": flavor_ref,
            "image_ref": image_ref,
            "vpc_id": vpc_id,
            "subnet_id": subnet_id,
            "root_volume_type": root_volume_type,
            "root_volume_size": root_volume_size,
            "availability_zone": availability_zone,
            "description": description,
            "auth": "key_name" if key_name else "admin_pass",
            "security_group_id": security_group_id,
            "public_ip": self._describe_public_ip(eip_bandwidth),
            "user_data": user_data,
            "period_type": period_type,
            "period_num": period_num,
            "is_auto_pay": is_auto_pay,
            "is_auto_renew": is_auto_renew,
            "is_auto_rename": is_auto_rename,
            "defaults_applied": defaults,
        }
        if subnet is not None:
            preview["subnet"] = {
                "name": subnet.get("name"),
                "cidr": subnet.get("cidr"),
            }
        if not confirm:
            return {
                "confirmation_required": True,
                "preview": preview,
                "message": (
                    f"Creating {count} prepaid ECS server(s) creates a billable order. "
                    "Review the preview. " + _CONFIRM_SUFFIX
                ),
            }
        job = await self._client.create_pre_paid_server(
            name=name,
            flavor_ref=flavor_ref,
            image_ref=image_ref,
            vpc_id=vpc_id,
            subnet_id=subnet_id,
            root_volume_type=root_volume_type,
            root_volume_size=root_volume_size,
            admin_pass=admin_pass,
            key_name=key_name,
            count=count,
            availability_zone=availability_zone,
            description=description,
            user_data=user_data,
            security_group_id=security_group_id,
            eip_bandwidth=eip_bandwidth,
            period_type=period_type,
            period_num=period_num,
            is_auto_pay=is_auto_pay,
            is_auto_renew=is_auto_renew,
            is_auto_rename=is_auto_rename,
        )
        return {
            "job_id": job.get("job_id"),
            "order_id": job.get("order_id"),
            "server_ids": job.get("server_ids") or [],
            "hints": [
                "Payment is manual by default: pay the order in the console before the "
                "servers are provisioned."
                if not is_auto_pay
                else "The order is paid automatically from the account balance.",
                "Call show_job with the job_id to track creation progress.",
            ],
        }

    async def create_on_demand_server(
        self,
        *,
        name: str,
        flavor_ref: str,
        image_ref: str,
        vpc_id: str | None = None,
        subnet_id: str | None = None,
        root_volume_type: str | None = None,
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
        confirm: bool = False,
    ) -> dict[str, Any]:
        self._validate_create_args(
            count=count, admin_pass=admin_pass, key_name=key_name, eip_bandwidth=eip_bandwidth
        )
        user_data = _encode_user_data(user_data)
        vpc_id, subnet_id, root_volume_type, defaults, subnet = await self._resolve_defaults(
            vpc_id, subnet_id, root_volume_type
        )
        preview: dict[str, Any] = {
            "operation": "create_on_demand_server",
            "billing": "postPaid (pay-per-use, billed per second while running)",
            "name": name,
            "count": count,
            "flavor_ref": flavor_ref,
            "image_ref": image_ref,
            "vpc_id": vpc_id,
            "subnet_id": subnet_id,
            "root_volume_type": root_volume_type,
            "root_volume_size": root_volume_size,
            "availability_zone": availability_zone,
            "description": description,
            "auth": "key_name" if key_name else "admin_pass",
            "security_group_id": security_group_id,
            "public_ip": self._describe_public_ip(eip_bandwidth),
            "user_data": user_data,
            "is_auto_rename": is_auto_rename,
            "defaults_applied": defaults,
        }
        if subnet is not None:
            preview["subnet"] = {
                "name": subnet.get("name"),
                "cidr": subnet.get("cidr"),
            }
        if not confirm:
            return {
                "confirmation_required": True,
                "preview": preview,
                "message": (
                    f"Creating {count} on-demand ECS server(s) starts per-second billing "
                    "immediately after creation. Review the preview. " + _CONFIRM_SUFFIX
                ),
            }
        job = await self._client.create_post_paid_server(
            name=name,
            flavor_ref=flavor_ref,
            image_ref=image_ref,
            vpc_id=vpc_id,
            subnet_id=subnet_id,
            root_volume_type=root_volume_type,
            root_volume_size=root_volume_size,
            admin_pass=admin_pass,
            key_name=key_name,
            count=count,
            availability_zone=availability_zone,
            description=description,
            user_data=user_data,
            security_group_id=security_group_id,
            eip_bandwidth=eip_bandwidth,
            is_auto_rename=is_auto_rename,
        )
        return {
            "job_id": job.get("job_id"),
            "server_ids": job.get("server_ids") or [],
            "hints": [
                "Billing starts as soon as each server is created; delete unused servers.",
                "Call show_job with the job_id to track creation progress.",
            ],
        }

    async def update_server(
        self,
        *,
        server_id: str,
        name: str | None = None,
        description: str | None = None,
        hostname: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        changes = {
            key: value
            for key, value in (("name", name), ("description", description), ("hostname", hostname))
            if value is not None
        }
        if not changes:
            raise McpToolError(
                "MCP_INVALID_ARGS",
                "At least one of name, description or hostname must be provided.",
                hint="Pass the field(s) you want to change; omitted fields stay unchanged.",
            )
        if not confirm:
            current = await self._find_server(server_id)
            return {
                "confirmation_required": True,
                "preview": {
                    "operation": "update_server",
                    "server_id": server_id,
                    "name": current.get("name"),
                    "tags": current.get("tags") or [],
                    "changes": {
                        key: {"current": current.get(key), "new": value}
                        for key, value in changes.items()
                    },
                },
                "message": "This changes the server metadata. Review the preview. "
                + _CONFIRM_SUFFIX,
            }
        current = await self._find_server(server_id)
        assert_not_protected(
            {
                "id": server_id,
                "name": str(current.get("name") or ""),
                "tags": current.get("tags") or [],
            },
            tool_name="update_server",
        )
        await self._client.update_server(
            server_id=server_id, name=name, description=description, hostname=hostname
        )
        return {
            "server_id": server_id,
            "updated": True,
            "changes": changes,
            "hints": ["Name changes propagate to the OS hostname only on reboot."],
        }

    async def delete_servers(
        self,
        *,
        server_ids: list[str],
        delete_volume: bool = False,
        delete_publicip: bool = False,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if not server_ids:
            raise McpToolError(
                "MCP_INVALID_ARGS", "server_ids must contain at least one server id."
            )
        unique_ids = list(dict.fromkeys(server_ids))
        servers = await self._fetch()
        by_id = {str(server.get("id") or ""): server for server in servers}
        matched: list[dict[str, Any]] = []
        not_found: list[str] = []
        for server_id in unique_ids:
            server = by_id.get(server_id)
            if server is None:
                not_found.append(server_id)
            else:
                matched.append(
                    {
                        "id": server_id,
                        "name": server.get("name"),
                        "status": server.get("status"),
                        "tags": server.get("tags") or [],
                    }
                )
        if not confirm:
            consequence = (
                "Data disks and the EIP are deleted together with the servers."
                if delete_volume and delete_publicip
                else "Data disks are kept and detached; the EIP is unbound and kept."
            )
            return {
                "confirmation_required": True,
                "preview": {
                    "operation": "delete_servers",
                    "servers": matched,
                    "not_found": not_found,
                    "delete_volume": delete_volume,
                    "delete_publicip": delete_publicip,
                    "consequence": consequence,
                },
                "message": (
                    f"Deleting {len(matched)} server(s) is irreversible. Review the preview. "
                    + _CONFIRM_SUFFIX
                ),
            }
        if not_found:
            raise McpToolError(
                "MCP_NOT_FOUND",
                f"Server(s) not found in this region: {', '.join(not_found)}.",
                hint="Nothing was deleted; remove unknown ids and retry.",
            )
        for server in matched:
            assert_not_protected(server, tool_name="delete_servers")
        job = await self._client.delete_servers(
            server_ids=unique_ids, delete_volume=delete_volume, delete_publicip=delete_publicip
        )
        return {
            "job_id": job.get("job_id"),
            "server_ids": unique_ids,
            "hints": [
                "Call show_job with the job_id to track deletion progress."
            ],
        }

    # -------------------------------------------------------------- internal

    async def _resolve_defaults(
        self,
        vpc_id: str | None,
        subnet_id: str | None,
        root_volume_type: str | None,
    ) -> tuple[str, str, str, list[str], dict[str, Any] | None]:
        """Fill omitted network/disk choices with server-side defaults.

        Both preview and confirm branches call this, so the preview always shows
        the exact configuration that would be executed.
        """
        defaults: list[str] = []
        subnet_detail: dict[str, Any] | None = None
        if not subnet_id:
            subnets = await self._client.list_subnets()
            if not subnets:
                raise McpToolError(
                    "MCP_NOT_FOUND",
                    "No subnet found in this region; cannot pick a default network.",
                    hint="Pass subnet_id explicitly to create the server.",
                )
            chosen = min(subnets, key=lambda subnet: str(subnet.get("name") or ""))
            subnet_id = chosen.get("id")
            vpc_id = chosen.get("vpc_id")
            subnet_detail = chosen
            defaults.extend(["vpc_id", "subnet_id"])
        elif not vpc_id:
            # The create API needs the VPC owning the subnet; derive it from the
            # subnet catalog so users can pass just the subnet id.
            for subnet in await self._client.list_subnets():
                if subnet.get("id") == subnet_id:
                    vpc_id = subnet.get("vpc_id")
                    break
            if not vpc_id:
                raise McpToolError(
                    "MCP_NOT_FOUND",
                    f"Subnet {subnet_id} not found in this region.",
                    hint="Pass vpc_id explicitly, or omit both to use the default subnet.",
                )
            defaults.append("vpc_id")
        volume_type = root_volume_type or _DEFAULT_ROOT_VOLUME_TYPE
        if volume_type != root_volume_type:
            defaults.append("root_volume_type")
        if vpc_id is None or subnet_id is None:
            raise McpToolError(
                "MCP_INTERNAL",
                "Default network resolution left the VPC or subnet unspecified.",
                hint="Pass vpc_id/subnet_id explicitly, or omit both for the default.",
            )
        return vpc_id, subnet_id, volume_type, defaults, subnet_detail

    @staticmethod
    def _describe_public_ip(eip_bandwidth: int | None) -> str:
        if eip_bandwidth is None:
            return "none"
        return f"auto-assign {eip_bandwidth} Mbit/s EIP (billed by traffic)"

    async def _fetch(
        self,
        *,
        name: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all servers once, then apply in-memory filters (keeps preview and
        confirm branches consistent and avoids per-id round trips)."""
        servers = await self._client.list_all_servers()
        if status:
            wanted = status.upper()
            servers = [s for s in servers if str(s.get("status") or "").upper() == wanted]
        if name:
            wanted = name.lower()
            servers = [s for s in servers if wanted in str(s.get("name") or "").lower()]
        return servers

    async def _find_server(self, server_id: str) -> dict[str, Any]:
        servers = await self._fetch()
        for server in servers:
            if str(server.get("id") or "") == server_id:
                return server
        raise McpToolError("MCP_NOT_FOUND", f"Server {server_id} not found in this region.")

    @staticmethod
    def _validate_create_args(
        *,
        count: int,
        admin_pass: str | None,
        key_name: str | None,
        period_type: str = "month",
        period_num: int = 1,
        eip_bandwidth: int | None = None,
    ) -> None:
        if count < 1 or count > _MAX_BATCH_COUNT:
            raise McpToolError(
                "MCP_INVALID_ARGS", f"count must be between 1 and {_MAX_BATCH_COUNT}."
            )
        if not admin_pass and not key_name:
            raise McpToolError(
                "MCP_INVALID_ARGS",
                "Either admin_pass or key_name must be provided as the login credential.",
            )
        if period_type not in ("month", "year"):
            raise McpToolError("MCP_INVALID_ARGS", "period_type must be 'month' or 'year'.")
        valid_periods = range(1, 10) if period_type == "month" else range(1, 4)
        if period_num not in valid_periods:
            bound = 9 if period_type == "month" else 3
            raise McpToolError(
                "MCP_INVALID_ARGS", f"period_num must be between 1 and {bound} for {period_type}."
            )
        low, high = _EIP_BANDWIDTH_RANGE
        if eip_bandwidth is not None and not low <= eip_bandwidth <= high:
            raise McpToolError(
                "MCP_INVALID_ARGS",
                f"eip_bandwidth must be between {low} and {high} Mbit/s.",
            )
