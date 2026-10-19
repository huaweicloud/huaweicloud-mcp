"""Tests for the RC client layer (SDK request assembly and error mapping).

These tests construct real SDK request objects, so they require
huaweicloudsdkrc to be installed; they are skipped otherwise via
pytest.importorskip at the top of each test. The service/tools layers are
tested with injected fakes and do not need the SDK.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.errors import McpToolError

from mcp_server_rc.client.rc_client import RcClient, sdk_to_dict

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

    def run_query(self, request: Any) -> dict[str, Any]:
        return self._record("run_query", request)

    def list_all_providers(self, request: Any) -> dict[str, Any]:
        return self._record("list_all_providers", request)

    def list_all_resources(self, request: Any) -> dict[str, Any]:
        return self._record("list_all_resources", request)

    def show_resource_detail(self, request: Any) -> dict[str, Any]:
        return self._record("show_resource_detail", request)

    def list_all_tags(self, request: Any) -> dict[str, Any]:
        return self._record("list_all_tags", request)

    def count_all_resources(self, request: Any) -> dict[str, Any]:
        return self._record("count_all_resources", request)

    def collect_all_resources_summary(self, request: Any) -> dict[str, Any]:
        return self._record("collect_all_resources_summary", request)

    def create_resource_group(self, request: Any) -> dict[str, Any]:
        return self._record("create_resource_group", request)

    def delete_resource_group(self, request: Any) -> dict[str, Any]:
        return self._record("delete_resource_group", request)

    def update_resource_group(self, request: Any) -> dict[str, Any]:
        return self._record("update_resource_group", request)

    def show_resource_group(self, request: Any) -> dict[str, Any]:
        return self._record("show_resource_group", request)

    def list_resource_groups(self, request: Any) -> dict[str, Any]:
        return self._record("list_resource_groups", request)

    def add_resources_to_group(self, request: Any) -> dict[str, Any]:
        return self._record("add_resources_to_group", request)

    def remove_resource_from_group(self, request: Any) -> dict[str, Any]:
        return self._record("remove_resource_from_group", request)

    def show_resource_relations(self, request: Any) -> dict[str, Any]:
        return self._record("show_resource_relations", request)

    def create_stored_query(self, request: Any) -> dict[str, Any]:
        return self._record("create_stored_query", request)

    def list_stored_queries(self, request: Any) -> dict[str, Any]:
        return self._record("list_stored_queries", request)

    def show_stored_query(self, request: Any) -> dict[str, Any]:
        return self._record("show_stored_query", request)

    def update_stored_query(self, request: Any) -> dict[str, Any]:
        return self._record("update_stored_query", request)

    def delete_stored_query(self, request: Any) -> dict[str, Any]:
        return self._record("delete_stored_query", request)


def _client(sdk: Any) -> RcClient:
    return RcClient(settings=_SETTINGS, sdk_client=sdk)


async def test_run_query_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    result = await _client(sdk).run_query(expression="SELECT * FROM resources")
    assert result == {"recorded": "run_query"}
    method, request = sdk.requests[0]
    assert method == "run_query"
    assert request.body.expression == "SELECT * FROM resources"


async def test_list_providers_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    result = await _client(sdk).list_providers(offset=0, limit=50, x_language="zh-cn")
    assert result == {"recorded": "list_all_providers"}
    method, request = sdk.requests[0]
    assert method == "list_all_providers"
    assert request.offset == 0
    assert request.limit == 50
    assert request.x_language == "zh-cn"


async def test_run_query_wraps_sdk_errors() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class BrokenSdk(RecordingSdkClient):
        def run_query(self, request: Any) -> dict[str, Any]:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 500
            exc.error_code = "RC.1000"
            exc.error_msg = "internal error"
            exc.request_id = "req-1"
            raise exc

    with pytest.raises(McpToolError) as excinfo:
        await _client(BrokenSdk()).run_query(expression="test")
    assert excinfo.value.code == "RC.1000"
    assert excinfo.value.request_id == "req-1"


async def test_run_query_5xx_error_has_query_hint() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class BrokenSdk(RecordingSdkClient):
        def run_query(self, request: Any) -> dict[str, Any]:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 500
            exc.error_code = "RC.00010500"
            exc.error_msg = "Internal server error occurred"
            exc.request_id = "req-2"
            raise exc

    with pytest.raises(McpToolError) as excinfo:
        await _client(BrokenSdk()).run_query(expression="bad sql")
    assert excinfo.value.code == "RC.00010500"
    assert "ResourceQL syntax" in (excinfo.value.hint or "")
    assert "simpler expression" in (excinfo.value.hint or "")


async def test_permission_error_has_iam_hint() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class BrokenSdk(RecordingSdkClient):
        def list_all_providers(self, request: Any) -> dict[str, Any]:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 403
            exc.error_code = "RC.00020002"
            exc.error_msg = (
                "User: iam::d46063b5305e4910b509c15b9d2b39a1:user:test is not "
                "authorized to perform: resourcecenter::listResource on resource: "
                "* because no identity-based policy allows the action."
            )
            exc.request_id = "req-4"
            raise exc

    with pytest.raises(McpToolError) as excinfo:
        await _client(BrokenSdk()).list_providers()
    assert excinfo.value.code == "RC.00020002"
    assert "IAM" in (excinfo.value.hint or "")
    assert "policy" in (excinfo.value.hint or "")


async def test_run_query_4xx_error_keeps_default_hint() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class BrokenSdk(RecordingSdkClient):
        def run_query(self, request: Any) -> dict[str, Any]:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 400
            exc.error_code = "RC.00010025"
            exc.error_msg = "bad request"
            exc.request_id = "req-3"
            raise exc

    with pytest.raises(McpToolError) as excinfo:
        await _client(BrokenSdk()).run_query(expression="bad")
    assert excinfo.value.code == "RC.00010025"
    assert excinfo.value.hint is None


async def test_list_all_resources_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).list_all_resources(
        region_id="cn-north-4",
        resource_type="ecs.cloudservers",
        limit=20,
        marker="m-1",
        name="web",
        tags=["env=prod"],
    )
    method, request = sdk.requests[0]
    assert method == "list_all_resources"
    assert request.region_id == "cn-north-4"
    assert request.type == "ecs.cloudservers"
    assert request.limit == 20
    assert request.marker == "m-1"
    assert request.name == "web"
    assert request.tags == ["env=prod"]


async def test_show_resource_detail_maps_404_to_none() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class NotFoundSdk(RecordingSdkClient):
        def show_resource_detail(self, request: Any) -> dict[str, Any]:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 404
            raise exc

    assert await _client(NotFoundSdk()).show_resource_detail(resource_id="ghost") is None


async def test_list_all_tags_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).list_all_tags(key="env", limit=10, marker="m-1")
    method, request = sdk.requests[0]
    assert method == "list_all_tags"
    assert request.key == "env"
    assert request.limit == 10
    assert request.marker == "m-1"


async def test_count_all_resources_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).count_all_resources(
        id_="r-1",
        name="web",
        resource_type=["ecs.cloudservers"],
        region_id=["cn-north-4"],
    )
    method, request = sdk.requests[0]
    assert method == "count_all_resources"
    assert request.id == "r-1"
    assert request.name == "web"
    assert request.type == ["ecs.cloudservers"]
    assert request.region_id == ["cn-north-4"]


async def test_collect_all_resources_summary_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).collect_all_resources_summary(name="web")
    method, request = sdk.requests[0]
    assert method == "collect_all_resources_summary"
    assert request.name == "web"


async def test_create_resource_group_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).create_resource_group(group_name="web-grp", description="d")
    method, request = sdk.requests[0]
    assert method == "create_resource_group"
    assert request.body.group_name == "web-grp"
    assert request.body.description == "d"


async def test_delete_resource_group_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).delete_resource_group(group_id="g-1")
    method, request = sdk.requests[0]
    assert method == "delete_resource_group"
    assert request.group_id == "g-1"


async def test_update_resource_group_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).update_resource_group(group_id="g-1", description="new-desc")
    method, request = sdk.requests[0]
    assert method == "update_resource_group"
    assert request.group_id == "g-1"
    assert request.body.description == "new-desc"


async def test_list_resource_groups_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).list_resource_groups(limit=10, marker="m-1")
    method, request = sdk.requests[0]
    assert method == "list_resource_groups"
    assert request.limit == 10
    assert request.marker == "m-1"


async def test_add_resources_to_group_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).add_resources_to_group(group_id="g-1", resource_ids=["r-1", "r-2"])
    method, request = sdk.requests[0]
    assert method == "add_resources_to_group"
    assert request.group_id == "g-1"
    assert request.body.resource_ids == ["r-1", "r-2"]


async def test_remove_resource_from_group_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).remove_resource_from_group(group_id="g-1", resource_id="r-1")
    method, request = sdk.requests[0]
    assert method == "remove_resource_from_group"
    assert request.group_id == "g-1"
    assert request.resource_id == "r-1"


async def test_show_resource_relations_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).show_resource_relations(
        resource_id="r-1",
        related_resource_type="vpc.publicips",
        limit=10,
    )
    method, request = sdk.requests[0]
    assert method == "show_resource_relations"
    assert request.resource_id == "r-1"
    assert request.related_resource_type == "vpc.publicips"
    assert request.limit == 10


async def test_create_stored_query_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).create_stored_query(name="q1", expression="SELECT 1", description="d")
    method, request = sdk.requests[0]
    assert method == "create_stored_query"
    assert request.body.name == "q1"
    assert request.body.expression == "SELECT 1"
    assert request.body.description == "d"


async def test_list_stored_queries_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).list_stored_queries(limit=10, name="q1")
    method, request = sdk.requests[0]
    assert method == "list_stored_queries"
    assert request.limit == 10
    assert request.name == "q1"


async def test_show_stored_query_maps_404_to_none() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class NotFoundSdk(RecordingSdkClient):
        def show_stored_query(self, request: Any) -> dict[str, Any]:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 404
            raise exc

    assert await _client(NotFoundSdk()).show_stored_query(query_id="ghost") is None


async def test_update_stored_query_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).update_stored_query(query_id="q-1", name="q2", expression="SELECT 2")
    method, request = sdk.requests[0]
    assert method == "update_stored_query"
    assert request.query_id == "q-1"
    assert request.body.name == "q2"
    assert request.body.expression == "SELECT 2"


async def test_delete_stored_query_request() -> None:
    pytest.importorskip("huaweicloudsdkrc")
    sdk = RecordingSdkClient()
    await _client(sdk).delete_stored_query(query_id="q-1")
    method, request = sdk.requests[0]
    assert method == "delete_stored_query"
    assert request.query_id == "q-1"


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


def test_sdk_to_dict_handles_objects_without_dict() -> None:
    assert isinstance(sdk_to_dict(object()), str)
    assert sdk_to_dict(b"bytes-value") == "bytes-value"
    assert isinstance(sdk_to_dict(datetime.datetime.now()), str)


def test_sdk_to_dict_prefers_sdk_to_dict_method() -> None:
    class ModelWithPrivateField:
        def to_dict(self) -> dict[str, Any]:
            return {"name": "instances", "_global": False, "regions": []}

    result = sdk_to_dict(ModelWithPrivateField())
    assert result == {"name": "instances", "global": False, "regions": []}
    assert "ResourceTypeResponse__global" not in result


def test_missing_credentials_raise_mcp_tool_error() -> None:
    empty = McpSettings(access_key="", secret_key="", region="")
    with pytest.raises(McpToolError) as excinfo:
        RcClient(settings=empty)
    assert excinfo.value.code == "MCP_INVALID_ARGS"
    assert "HUAWEICLOUD_REGION" not in (excinfo.value.message or "")
    assert "does not require" in (excinfo.value.hint or "")


def test_region_not_required_for_global_service() -> None:
    no_region = McpSettings(
        access_key="AKTESTKEY000001",
        secret_key="sk" + "0" * 38,
        region="",
    )
    client = RcClient(settings=no_region, sdk_client=RecordingSdkClient())
    assert client._settings.region == ""
