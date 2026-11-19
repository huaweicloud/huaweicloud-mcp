# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the ECS lifecycle client layer (pagination, SDK mapping, errors)."""

from __future__ import annotations

from typing import Any

import pytest
from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.errors import McpToolError

from mcp_huaweicloud_ecs_lifecycle.client.ecs_lifecycle_client import EcsLifecycleClient

_SETTINGS = McpSettings(
    access_key="AKTESTKEY000001",
    secret_key="sk" + "0" * 38,
    region="cn-north-4",
)


class RecordingSdkClient:
    """Fake SDK client: canned responses for every method, records requests."""

    def __init__(
        self,
        pages: list[list[dict[str, Any]]] | None = None,
        response: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.pages = pages or []
        self.response = response if response is not None else {}
        self.error = error
        self.requests: list[Any] = []

    def _respond(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response

    def list_servers_details(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        page_index = len(self.requests) - 1
        return {"servers": self.pages[page_index] if page_index < len(self.pages) else []}

    def show_server(self, request: Any) -> dict[str, Any]:
        return self._respond(request)

    def create_servers(self, request: Any) -> dict[str, Any]:
        return self._respond(request)

    def create_post_paid_servers(self, request: Any) -> dict[str, Any]:
        return self._respond(request)

    def update_server(self, request: Any) -> dict[str, Any]:
        return self._respond(request)

    def delete_servers(self, request: Any) -> dict[str, Any]:
        return self._respond(request)

    def show_job(self, request: Any) -> dict[str, Any]:
        return self._respond(request)

    def list_images(self, request: Any) -> dict[str, Any]:
        return self._respond(request)

    def list_flavors(self, request: Any) -> dict[str, Any]:
        return self._respond(request)

    def nova_list_keypairs(self, request: Any) -> dict[str, Any]:
        return self._respond(request)

    def list_subnets(self, request: Any) -> dict[str, Any]:
        return self._respond(request)


def _client(sdk: Any) -> EcsLifecycleClient:
    return EcsLifecycleClient(settings=_SETTINGS, sdk_client=sdk)


def _server(server_id: str) -> dict[str, Any]:
    return {"id": server_id, "name": server_id, "status": "ACTIVE"}


async def test_list_all_servers_single_page() -> None:
    sdk = RecordingSdkClient(pages=[[_server("s-1"), _server("s-2")]])
    result = await _client(sdk).list_all_servers()
    assert [s["id"] for s in result] == ["s-1", "s-2"]
    assert len(sdk.requests) == 1
    assert sdk.requests[0].limit == 1000
    assert sdk.requests[0].offset == 1


async def test_list_all_servers_multi_page() -> None:
    page = [_server(f"s-{i}") for i in range(1000)]
    sdk = RecordingSdkClient(pages=[page, [_server("s-tail")]])
    result = await _client(sdk).list_all_servers()
    assert len(result) == 1001
    assert result[1000]["id"] == "s-tail"
    assert len(sdk.requests) == 2
    assert [r.offset for r in sdk.requests] == [1, 2]


async def test_list_all_servers_empty_region() -> None:
    sdk = RecordingSdkClient(pages=[])
    result = await _client(sdk).list_all_servers()
    assert result == []
    assert len(sdk.requests) == 1


async def test_list_all_servers_wraps_client_request_error() -> None:
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ClientRequestException

    def _boom(request: Any) -> dict[str, Any]:
        exc = ClientRequestException.__new__(ClientRequestException)
        exc.status_code = 401
        exc.error_code = "Common.0203"
        exc.error_msg = "incorrect iam authentication information"
        exc.request_id = "req-2"
        raise exc

    sdk = RecordingSdkClient()
    sdk.list_servers_details = _boom  # type: ignore[method-assign]
    with pytest.raises(McpToolError) as excinfo:
        await _client(sdk).list_all_servers()
    assert excinfo.value.code == "Common.0203"
    assert excinfo.value.request_id == "req-2"


async def test_list_all_servers_wraps_connection_failures() -> None:
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ConnectionException

    class UnreachableSdk(RecordingSdkClient):
        def list_servers_details(self, request: Any) -> dict[str, Any]:
            raise ConnectionException("proxy CONNECT tunnel failed, response 504")

    with pytest.raises(McpToolError) as excinfo:
        await _client(UnreachableSdk()).list_all_servers()
    assert excinfo.value.code == "MCP_SDK_ERROR"
    assert "CONNECT tunnel failed" in excinfo.value.message


# ------------------------------------------------------------------- discovery


class _ImagePagingSdk(RecordingSdkClient):
    """list_images fake returning a fixed page sequence in call order."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        super().__init__()
        self.image_pages = pages

    def list_images(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        return self.image_pages[len(self.requests) - 1]


async def test_list_images_pages_until_marker_exhausted() -> None:
    pytest.importorskip("huaweicloudsdkims")
    sdk = _ImagePagingSdk(
        [
            {
                "images": [
                    {"id": "img-1", "name": "Ubuntu 22.04"},
                    {"id": "img-2", "name": "CentOS 7"},
                ],
                "page_info": {"next_marker": "marker-2"},
            },
            {"images": [{"id": "img-3", "name": "Windows 2019"}], "page_info": {}},
        ]
    )

    result = await _client(sdk).list_images()

    assert [i["id"] for i in result] == ["img-1", "img-2", "img-3"]
    assert len(sdk.requests) == 2
    assert sdk.requests[0].limit == 100
    assert sdk.requests[0].marker is None
    assert sdk.requests[1].marker == "marker-2"


async def test_list_flavors_maps_flavors_key() -> None:
    pytest.importorskip("huaweicloudsdkecs")
    flavors = [{"id": "s6.small.1", "name": "s6.small.1", "vcpus": "1", "ram": 1024, "disk": 40}]
    sdk = RecordingSdkClient(response={"flavors": flavors})

    result = await _client(sdk).list_flavors()

    assert result == flavors
    assert sdk.requests[0].limit == 1000


class _FlavorPagingSdk(RecordingSdkClient):
    """list_flavors fake returning a fixed page sequence in call order."""

    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        super().__init__()
        self.flavor_pages = pages

    def list_flavors(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        return {"flavors": self.flavor_pages[len(self.requests) - 1]}


async def test_list_flavors_pages_until_short_page() -> None:
    pytest.importorskip("huaweicloudsdkecs")
    page = [
        {"id": f"f-{i}", "name": f"f-{i}", "vcpus": "1", "ram": 1024, "disk": 40}
        for i in range(1000)
    ]
    tail = [{"id": "x1.1u.1g", "name": "x1.1u.1g", "vcpus": "1", "ram": 1024, "disk": 0}]
    sdk = _FlavorPagingSdk([page, tail])

    result = await _client(sdk).list_flavors()

    assert len(result) == 1001
    assert result[-1]["id"] == "x1.1u.1g"
    assert len(sdk.requests) == 2
    assert sdk.requests[0].marker is None
    # Marker is the last id of the previous page: "next data after this flavor".
    assert sdk.requests[1].marker == "f-999"


async def test_list_flavors_forwards_flavor_id() -> None:
    pytest.importorskip("huaweicloudsdkecs")
    flavors = [{"id": "x1.1u.1g", "name": "x1.1u.1g", "vcpus": "1", "ram": 1024, "disk": 0}]
    sdk = RecordingSdkClient(response={"flavors": flavors})

    result = await _client(sdk).list_flavors(flavor_id="x1.1u.1g")

    assert result == flavors
    assert sdk.requests[0].flavor_id == "x1.1u.1g"


async def test_list_keypairs_keeps_nova_nested_shape() -> None:
    pytest.importorskip("huaweicloudsdkecs")
    nested = [{"keypair": {"name": "kp-1", "fingerprint": "aa:bb", "type": "ssh"}}]
    sdk = RecordingSdkClient(response={"keypairs": nested})

    result = await _client(sdk).list_keypairs()

    assert result == nested
    assert len(sdk.requests) == 1


async def test_list_subnets_maps_subnets_key() -> None:
    pytest.importorskip("huaweicloudsdkvpc")
    subnets = [{"id": "subnet-1", "name": "alpha", "cidr": "10.0.0.0/24", "vpc_id": "vpc-1"}]
    sdk = RecordingSdkClient(response={"subnets": subnets})

    result = await _client(sdk).list_subnets()

    assert result == subnets
    assert sdk.requests[0].limit == 1000


async def test_list_subnets_pages_until_short_page() -> None:
    pytest.importorskip("huaweicloudsdkvpc")
    page = [{"id": f"subnet-{i}", "name": f"n{i}", "cidr": "10.0.0.0/24"} for i in range(1000)]
    tail = [{"id": "subnet-tail", "name": "tail", "cidr": "10.0.1.0/24"}]

    class _SubnetPagingSdk(RecordingSdkClient):
        def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
            super().__init__()
            self.subnet_pages = pages

        def list_subnets(self, request: Any) -> dict[str, Any]:
            self.requests.append(request)
            return {"subnets": self.subnet_pages[len(self.requests) - 1]}

    sdk = _SubnetPagingSdk([page, tail])
    result = await _client(sdk).list_subnets()

    assert len(result) == 1001
    assert result[-1]["id"] == "subnet-tail"
    assert len(sdk.requests) == 2
    assert sdk.requests[1].marker == "subnet-999"


async def test_injected_sdk_routes_every_service() -> None:
    pytest.importorskip("huaweicloudsdkvpc")
    subnets = [{"id": "subnet-1", "name": "alpha", "cidr": "10.0.0.0/24", "vpc_id": "vpc-1"}]
    sdk = RecordingSdkClient(response={"subnets": subnets})
    client = EcsLifecycleClient(settings=_SETTINGS, sdk_client=sdk)

    # Without an injected SDK each service would get its own client; the test
    # seam routes ims/vpc calls to the same stub.
    assert client._service_client("ecs") is sdk
    assert client._service_client("ims") is sdk
    assert client._service_client("vpc") is sdk
    assert await client.list_subnets() == subnets


async def test_create_pre_paid_server_maps_flat_params_to_sdk_models() -> None:
    pytest.importorskip("huaweicloudsdkecs")
    sdk = RecordingSdkClient(
        response={"job_id": "job-1", "order_id": "order-1", "server_ids": ["srv-1", "srv-2"]}
    )
    result = await _client(sdk).create_pre_paid_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="GPSSD",
        count=2,
        period_type="month",
        period_num=3,
        is_auto_pay=True,
        is_auto_renew=False,
    )
    assert result == {"job_id": "job-1", "order_id": "order-1", "server_ids": ["srv-1", "srv-2"]}
    server = sdk.requests[0].body.server
    assert server.name == "web"
    assert server.flavor_ref == "c7.large.2"
    assert server.image_ref == "img-1"
    assert server.vpcid == "vpc-1"
    assert server.nics[0].subnet_id == "subnet-1"
    assert server.root_volume.volumetype == "GPSSD"
    assert server.count == 2
    # The API expects "true"/"false" strings for these flags, not booleans.
    assert server.extendparam.is_auto_pay == "true"
    assert server.extendparam.is_auto_renew == "false"
    assert server.extendparam.period_type == "month"
    assert server.extendparam.period_num == 3


async def test_create_post_paid_server_sets_charging_mode_zero() -> None:
    pytest.importorskip("huaweicloudsdkecs")
    sdk = RecordingSdkClient(response={"job_id": "job-2", "server_ids": ["srv-3"]})
    result = await _client(sdk).create_post_paid_server(
        name="batch",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="SSD",
    )
    assert result == {"job_id": "job-2", "server_ids": ["srv-3"]}
    server = sdk.requests[0].body.server
    assert server.name == "batch"
    # charging_mode 0 = pay-per-use; extendparam is required for post-paid.
    assert server.extendparam.charging_mode == 0


async def test_create_pre_paid_server_assembles_eip_sg_and_user_data() -> None:
    pytest.importorskip("huaweicloudsdkecs")
    sdk = RecordingSdkClient(response={"job_id": "job-4"})
    await _client(sdk).create_pre_paid_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="SSD",
        user_data="IyEvYmluL2Jhc2gK",
        security_group_id="sg-1",
        eip_bandwidth=10,
    )
    server = sdk.requests[0].body.server
    assert server.user_data == "IyEvYmluL2Jhc2gK"
    assert server.security_groups[0].id == "sg-1"
    assert server.publicip.eip.iptype == "5_bgp"
    assert server.publicip.eip.bandwidth.size == 10
    assert server.publicip.eip.bandwidth.sharetype == "PER"
    assert server.publicip.eip.bandwidth.chargemode == "traffic"
    assert server.publicip.delete_on_termination is True


async def test_create_post_paid_server_omits_publicip_without_bandwidth() -> None:
    pytest.importorskip("huaweicloudsdkecs")
    sdk = RecordingSdkClient(response={"job_id": "job-5"})
    await _client(sdk).create_post_paid_server(
        name="batch",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="SSD",
        security_group_id="sg-2",
    )
    server = sdk.requests[0].body.server
    assert server.publicip is None
    assert server.security_groups[0].id == "sg-2"
    assert server.user_data is None


async def test_delete_servers_builds_id_list_and_flags() -> None:
    pytest.importorskip("huaweicloudsdkecs")
    sdk = RecordingSdkClient(response={"job_id": "job-3"})
    await _client(sdk).delete_servers(
        server_ids=["a", "b"], delete_volume=True, delete_publicip=True
    )
    body = sdk.requests[0].body
    assert body.delete_volume is True
    assert body.delete_publicip is True
    assert [item.id for item in body.servers] == ["a", "b"]


async def test_update_server_passes_only_given_fields() -> None:
    pytest.importorskip("huaweicloudsdkecs")
    sdk = RecordingSdkClient()
    await _client(sdk).update_server(server_id="srv-1", name="web-2")
    option = sdk.requests[0].body.server
    assert option.name == "web-2"
    assert option.description is None
    assert option.hostname is None


class _FakeBuilder:
    def __init__(self) -> None:
        self.regions: list[Any] = []
        self.http_config: Any = None

    def with_credentials(self, credentials: Any) -> _FakeBuilder:
        return self

    def with_region(self, region: Any) -> _FakeBuilder:
        self.regions.append(region)
        return self

    def with_http_config(self, config: Any) -> _FakeBuilder:
        self.http_config = config
        return self

    def build(self) -> str:
        return "built"


class _FakeSdkEcsClient:
    last_builder: _FakeBuilder | None = None

    @staticmethod
    def new_builder() -> _FakeBuilder:
        builder = _FakeBuilder()
        _FakeSdkEcsClient.last_builder = builder
        return builder


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    region: str,
    endpoint: str | None = None,
    skip_regions_env: str | None = None,
) -> _FakeBuilder:
    pytest.importorskip("huaweicloudsdkecs")
    import huaweicloudsdkecs.v2 as sdk_v2

    monkeypatch.setattr(sdk_v2, "EcsClient", _FakeSdkEcsClient)
    if skip_regions_env is not None:
        monkeypatch.setenv("HUAWEICLOUD_MCP_SKIP_SSL_VERIFY_REGIONS", skip_regions_env)
    settings = McpSettings(
        access_key="AKTESTKEY000001",
        secret_key="sk" + "0" * 38,
        region=region,
        # skips the IAM project_id lookup, which would hit the real network
        project_id="00000000000000000000000000000000",
        endpoint=endpoint,
    )
    EcsLifecycleClient(settings=settings)
    builder = _FakeSdkEcsClient.last_builder
    assert builder is not None
    return builder


def test_client_synthesizes_region_outside_sdk_map(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = _build_client(monkeypatch, region="cn-southwest-242")
    assert len(builder.regions) == 1
    assert builder.regions[0].id == "cn-southwest-242"
    assert builder.regions[0].endpoint == "https://ecs.cn-southwest-242.myhuaweicloud.com"


def test_client_endpoint_override_beats_region_map(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = _build_client(monkeypatch, region="cn-north-4", endpoint="ecs.example.com")
    assert builder.regions[0].id == "cn-north-4"
    assert builder.regions[0].endpoint == "https://ecs.example.com"


def test_client_uses_sdk_region_map_when_known(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = _build_client(monkeypatch, region="cn-north-4")
    assert builder.regions[0].id == "cn-north-4"


class _FakeSdkImsClient:
    last_builder: _FakeBuilder | None = None

    @staticmethod
    def new_builder() -> _FakeBuilder:
        builder = _FakeBuilder()
        _FakeSdkImsClient.last_builder = builder
        return builder


class _FakeSdkVpcClient:
    last_builder: _FakeBuilder | None = None

    @staticmethod
    def new_builder() -> _FakeBuilder:
        builder = _FakeBuilder()
        _FakeSdkVpcClient.last_builder = builder
        return builder


def _endpoint_for_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    service: str,
    region: str,
    endpoint: str | None = None,
    skip_regions_env: str | None = None,
) -> _FakeBuilder:
    """Build a real client and return the fake builder used for ``service``.

    Patches the ECS client class so ``__init__`` stays offline, then the
    service-specific class so the lazy build records its Region.
    """
    pytest.importorskip("huaweicloudsdkecs")
    import huaweicloudsdkecs.v2 as ecs_v2

    monkeypatch.setattr(ecs_v2, "EcsClient", _FakeSdkEcsClient)
    if skip_regions_env is not None:
        monkeypatch.setenv("HUAWEICLOUD_MCP_SKIP_SSL_VERIFY_REGIONS", skip_regions_env)
    settings = McpSettings(
        access_key="AKTESTKEY000001",
        secret_key="sk" + "0" * 38,
        region=region,
        project_id="00000000000000000000000000000000",
        endpoint=endpoint,
    )
    client = EcsLifecycleClient(settings=settings)
    if service == "ims":
        pytest.importorskip("huaweicloudsdkims")
        import huaweicloudsdkims.v2 as ims_v2

        monkeypatch.setattr(ims_v2, "ImsClient", _FakeSdkImsClient)
        client._service_client("ims")
        builder = _FakeSdkImsClient.last_builder
    else:
        pytest.importorskip("huaweicloudsdkvpc")
        import huaweicloudsdkvpc.v2 as vpc_v2

        monkeypatch.setattr(vpc_v2, "VpcClient", _FakeSdkVpcClient)
        client._service_client("vpc")
        builder = _FakeSdkVpcClient.last_builder
    assert builder is not None
    return builder


def test_ims_endpoint_swaps_service_label(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = _endpoint_for_service(
        monkeypatch,
        service="ims",
        region="cn-southwest-242",
        endpoint="ecs.cn-southwest-242.myhuaweicloud.com",
    )
    assert len(builder.regions) == 1
    assert builder.regions[0].id == "cn-southwest-242"
    assert builder.regions[0].endpoint == "https://ims.cn-southwest-242.myhuaweicloud.com"


def test_gateway_endpoint_is_shared_across_services(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = _endpoint_for_service(
        monkeypatch,
        service="vpc",
        region="cn-north-4",
        endpoint="https://gw.example.com",
    )
    assert builder.regions[0].id == "cn-north-4"
    assert builder.regions[0].endpoint == "https://gw.example.com"


def test_ims_endpoint_synthesized_without_override(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = _endpoint_for_service(monkeypatch, service="ims", region="cn-southwest-242")
    assert builder.regions[0].id == "cn-southwest-242"
    assert builder.regions[0].endpoint == "https://ims.cn-southwest-242.myhuaweicloud.com"


# ------------------------------------------------------------- TLS verification


def test_client_skips_ssl_verify_for_listed_region(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = _build_client(
        monkeypatch,
        region="cn-southwest-242",
        skip_regions_env="cn-southwest-242, cn-southwest-246",
    )
    assert builder.http_config is not None
    assert builder.http_config.ignore_ssl_verification is True


def test_client_keeps_ssl_verify_for_unlisted_region(monkeypatch: pytest.MonkeyPatch) -> None:
    # Region not in the skip list must keep strict TLS validation, even when
    # the env var names another region.
    builder = _build_client(
        monkeypatch,
        region="cn-north-4",
        skip_regions_env="cn-southwest-242",
    )
    assert builder.http_config is not None
    assert builder.http_config.ignore_ssl_verification is False


def test_client_keeps_ssl_verify_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = _build_client(monkeypatch, region="cn-southwest-242")
    assert builder.http_config is not None
    assert builder.http_config.ignore_ssl_verification is False


def test_ims_client_skips_ssl_verify_for_listed_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _endpoint_for_service(
        monkeypatch,
        service="ims",
        region="cn-southwest-242",
        skip_regions_env="cn-southwest-242",
    )
    assert builder.http_config is not None
    assert builder.http_config.ignore_ssl_verification is True


def test_vpc_client_keeps_ssl_verify_for_unlisted_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _endpoint_for_service(
        monkeypatch,
        service="vpc",
        region="cn-southwest-242",
        skip_regions_env="cn-north-4",
    )
    assert builder.http_config is not None
    assert builder.http_config.ignore_ssl_verification is False
