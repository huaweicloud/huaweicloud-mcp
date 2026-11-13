# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the ECS client layer (pagination, error mapping, dict conversion)."""

from __future__ import annotations

from typing import Any

import pytest
from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.errors import McpToolError

from mcp_server_ecs_readonly.client.ecs_client import EcsClient

_SETTINGS = McpSettings(
    access_key="AKTESTKEY000001",
    secret_key="sk" + "0" * 38,
    region="cn-north-4",
)


class RecordingSdkClient:
    """Fake SDK client that returns queued pages for list_servers_details."""

    def __init__(self, pages: list[list[dict[str, Any]]] | None = None) -> None:
        self.pages = pages or []
        self.requests: list[Any] = []

    def list_servers_details(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        page_index = len(self.requests) - 1
        return {"servers": self.pages[page_index] if page_index < len(self.pages) else []}


def _client(sdk: Any) -> EcsClient:
    return EcsClient(settings=_SETTINGS, sdk_client=sdk)


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


async def test_list_all_servers_stops_on_empty_page() -> None:
    page = [_server(f"s-{i}") for i in range(1000)]
    sdk = RecordingSdkClient(pages=[page, page])
    result = await _client(sdk).list_all_servers()
    assert len(result) == 2000
    assert len(sdk.requests) == 3


async def test_list_all_servers_empty_region() -> None:
    sdk = RecordingSdkClient(pages=[])
    result = await _client(sdk).list_all_servers()
    assert result == []
    assert len(sdk.requests) == 1


async def test_list_all_servers_wraps_sdk_error() -> None:
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class BrokenSdk(RecordingSdkClient):
        def list_servers_details(self, request: Any) -> dict[str, Any]:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 500
            exc.error_code = "Ecs.1000"
            exc.error_msg = "internal error"
            exc.request_id = "req-1"
            raise exc

    # 5xx is retryable: call_sdk retries once (default max_retries=1) before
    # surfacing MCP_SERVER_ERROR. The raw error_code (Ecs.1000) is no longer
    # the surfaced code — call_sdk wraps the sustained failure distinctly so
    # the Agent does not re-send at once.
    with pytest.raises(McpToolError) as excinfo:
        await _client(BrokenSdk()).list_all_servers()
    assert excinfo.value.code == "MCP_SERVER_ERROR"
    assert excinfo.value.request_id == "req-1"


async def test_list_all_servers_wraps_client_request_error() -> None:
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ClientRequestException

    class UnauthorizedSdk(RecordingSdkClient):
        def list_servers_details(self, request: Any) -> dict[str, Any]:
            exc = ClientRequestException.__new__(ClientRequestException)
            exc.status_code = 401
            exc.error_code = "Common.0203"
            exc.error_msg = "incorrect iam authentication information"
            exc.request_id = "req-2"
            raise exc

    with pytest.raises(McpToolError) as excinfo:
        await _client(UnauthorizedSdk()).list_all_servers()
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
    EcsClient(settings=settings)
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
