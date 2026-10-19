# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the RFS client layer (SDK request assembly and error mapping)."""

from __future__ import annotations

from typing import Any

import pytest
from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.errors import McpToolError

from mcp_server_rfs.client.rfs_client import RfsClient, sdk_to_dict

_SETTINGS = McpSettings(
    access_key="AKTESTKEY000001",
    secret_key="sk" + "0" * 38,
    region="cn-north-4",
)


class RecordingSdkClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, Any]] = []

    def _record(self, method: str, request: Any) -> dict[str, Any]:
        self.requests.append((method, request))
        return {"recorded": method}

    def list_stacks(self, request: Any) -> dict[str, Any]:
        return self._record("list_stacks", request)

    def get_stack_metadata(self, request: Any) -> dict[str, Any]:
        return self._record("get_stack_metadata", request)

    def create_stack(self, request: Any) -> dict[str, Any]:
        return self._record("create_stack", request)

    def deploy_stack(self, request: Any) -> dict[str, Any]:
        return self._record("deploy_stack", request)

    def delete_stack_enhanced(self, request: Any) -> dict[str, Any]:
        return self._record("delete_stack_enhanced", request)

    def list_stack_events(self, request: Any) -> dict[str, Any]:
        return self._record("list_stack_events", request)

    def list_stack_resources(self, request: Any) -> dict[str, Any]:
        return self._record("list_stack_resources", request)

    def list_stack_outputs(self, request: Any) -> dict[str, Any]:
        return self._record("list_stack_outputs", request)

    def create_execution_plan(self, request: Any) -> dict[str, Any]:
        return self._record("create_execution_plan", request)

    def get_execution_plan_metadata(self, request: Any) -> dict[str, Any]:
        return self._record("get_execution_plan_metadata", request)

    def get_execution_plan(self, request: Any) -> dict[str, Any]:
        return self._record("get_execution_plan", request)


def _client(sdk: Any) -> RfsClient:
    return RfsClient(settings=_SETTINGS, sdk_client=sdk)


async def test_list_stacks_request() -> None:
    sdk = RecordingSdkClient()
    result = await _client(sdk).list_stacks(limit=20, marker="m-1")
    assert result == {"recorded": "list_stacks"}
    method, request = sdk.requests[0]
    assert method == "list_stacks"
    assert request.limit == 20
    assert request.marker == "m-1"
    assert request.client_request_id  # RFS APIGW requires the Client-Request-Id header


async def test_create_stack_converts_variables() -> None:
    sdk = RecordingSdkClient()
    await _client(sdk).create_stack(
        stack_name="web",
        template_body="tpl",
        template_uri=None,
        variables={"env": "prod", "size": "3"},
        enable_deletion_protection=True,
    )
    _, request = sdk.requests[0]
    assert request.body.stack_name == "web"
    assert request.body.template_body == "tpl"
    assert request.body.enable_deletion_protection is True
    converted = [
        {"var_key": item.var_key, "var_value": item.var_value}
        for item in request.body.vars_structure
    ]
    assert converted == [
        {"var_key": "env", "var_value": "prod"},
        {"var_key": "size", "var_value": "3"},
    ]


async def test_deploy_stack_request() -> None:
    sdk = RecordingSdkClient()
    await _client(sdk).deploy_stack(
        stack_name="web", template_body=None, template_uri="obs://tpl", variables=None
    )
    _, request = sdk.requests[0]
    assert request.stack_name == "web"
    assert request.body.template_uri == "obs://tpl"
    assert request.body.vars_structure == []


async def test_get_execution_plan_metadata_request() -> None:
    sdk = RecordingSdkClient()
    await _client(sdk).get_execution_plan_metadata(stack_name="web", execution_plan_id="plan-1")
    _, request = sdk.requests[0]
    assert request.stack_name == "web"
    assert request.execution_plan_id == "plan-1"


async def test_delete_stack_request() -> None:
    sdk = RecordingSdkClient()
    await _client(sdk).delete_stack(stack_name="web", retain_all_resources=True)
    method, request = sdk.requests[0]
    assert method == "delete_stack_enhanced"
    assert request.stack_name == "web"
    assert request.body.retain_all_resources is True


async def test_get_execution_plan_request() -> None:
    sdk = RecordingSdkClient()
    await _client(sdk).get_execution_plan(stack_name="web", execution_plan_id="plan-1")
    _, request = sdk.requests[0]
    assert request.stack_name == "web"
    assert request.execution_plan_id == "plan-1"


async def test_get_stack_metadata_maps_404_to_none() -> None:
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class NotFoundSdk(RecordingSdkClient):
        def get_stack_metadata(self, request: Any) -> dict[str, Any]:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 404
            raise exc

    assert await _client(NotFoundSdk()).get_stack_metadata("ghost") is None


async def test_get_stack_metadata_wraps_other_errors() -> None:
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class BrokenSdk(RecordingSdkClient):
        def get_stack_metadata(self, request: Any) -> dict[str, Any]:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 500
            exc.error_code = "RFS.1000"
            exc.error_msg = "internal error"
            exc.request_id = "req-1"
            raise exc

    with pytest.raises(McpToolError) as excinfo:
        await _client(BrokenSdk()).get_stack_metadata("web")
    assert excinfo.value.code == "RFS.1000"
    assert excinfo.value.request_id == "req-1"


def test_sdk_to_dict_strips_private_prefixes() -> None:
    class Inner:
        def __init__(self) -> None:
            self._value = "v"

    class Outer:
        def __init__(self) -> None:
            self._name = "web"
            self._status = "OK"
            self._inner = Inner()
            self._items = [Inner(), Inner()]

    result = sdk_to_dict(Outer())
    assert result == {
        "name": "web",
        "status": "OK",
        "inner": {"value": "v"},
        "items": [{"value": "v"}, {"value": "v"}],
    }


def test_sdk_to_dict_passthrough_scalars() -> None:
    assert sdk_to_dict(None) is None
    assert sdk_to_dict("x") == "x"
    assert sdk_to_dict(5) == 5
    assert sdk_to_dict(True) is True
    assert sdk_to_dict({"a": [1, 2]}) == {"a": [1, 2]}


def test_sdk_to_dict_handles_real_sdk_response_with_raw_content() -> None:
    """Every SDK response inherits SdkResponse, which sets `_raw_content` (bytes).

    Previously `sdk_to_dict` called vars() on that bytes value and raised
    `TypeError: vars() argument must have __dict__ attribute`. This must not
    regress once a call finally returns real data.
    """
    pytest.importorskip("huaweicloudsdkrfs")
    from huaweicloudsdkrfs.v1.model.list_stacks_response import ListStacksResponse
    from huaweicloudsdkrfs.v1.model.stack import Stack

    resp = ListStacksResponse(
        stacks=[Stack(stack_name="web", stack_id="id-1", status="CREATION_COMPLETE")]
    )
    resp.status_code = 200
    resp.raw_content = b'{"stacks":[]}'  # exactly what SdkResponse stores

    out = sdk_to_dict(resp)

    # Transport-layer fields must NOT leak into tool output.
    assert "raw_content" not in out
    assert "status_code" not in out
    # Logical response fields are preserved.
    assert out["stacks"][0]["stack_name"] == "web"
    assert out["stacks"][0]["stack_id"] == "id-1"
    assert out["stacks"][0]["status"] == "CREATION_COMPLETE"


def test_sdk_to_dict_coerces_non_dict_objects_instead_of_crashing() -> None:
    """Objects without __dict__ (bytes, datetime, Decimal, ...) must not crash."""
    import datetime
    from decimal import Decimal

    # bytes (this is what _raw_content holds) -> coerced, not TypeError.
    assert isinstance(sdk_to_dict(b"raw"), str)
    assert isinstance(sdk_to_dict(datetime.datetime(2026, 1, 1)), str)
    assert isinstance(sdk_to_dict(Decimal("1.5")), str)


async def test_every_request_carries_client_request_id() -> None:
    """RFS APIGW rejects requests without the Client-Request-Id header (APIGW.0106)."""
    sdk = RecordingSdkClient()
    client = _client(sdk)

    await client.list_stacks(limit=10, marker=None)
    await client.get_stack_metadata("web")
    await client.create_stack(
        stack_name="web",
        template_body="tpl",
        template_uri=None,
        variables=None,
        enable_deletion_protection=False,
    )
    await client.deploy_stack(
        stack_name="web", template_body="tpl", template_uri=None, variables=None
    )
    await client.delete_stack(stack_name="web", retain_all_resources=False)
    await client.list_stack_events(stack_name="web", limit=5)
    await client.list_stack_resources(stack_name="web")
    await client.list_stack_outputs(stack_name="web")
    await client.create_execution_plan(
        stack_name="web", template_body="tpl", template_uri=None, variables=None
    )
    await client.get_execution_plan_metadata(stack_name="web", execution_plan_id="plan-1")
    await client.get_execution_plan(stack_name="web", execution_plan_id="plan-1")

    assert len(sdk.requests) == 11
    for method, request in sdk.requests:
        rid = getattr(request, "client_request_id", None)
        assert isinstance(rid, str) and rid, (
            f"{method} request missing client_request_id (RFS APIGW requires it)"
        )
        # RFS APIGW enforces 36-char dashed UUID form (RF.10011006 rejects the 32-char hex form).
        assert len(rid) == 36 and rid.count("-") == 4, (
            f"{method} client_request_id must be a 36-char UUID, got {rid!r}"
        )
