"""Tests for the RC tool layer: registration, guard declaration, invocation."""

from __future__ import annotations

from typing import Any

import pytest
from huaweicloud_mcp_core.security import ToolRisk, get_tool_risk, tool_supports_confirm

import mcp_server_rc.server  # noqa: F401  (import registers all tools)

_ALL_TOOLS = {
    # resource inventory
    "run_query": ToolRisk.READ,
    "list_providers": ToolRisk.READ,
    "list_all_resources": ToolRisk.READ,
    "show_resource_detail": ToolRisk.READ,
    "list_all_tags": ToolRisk.READ,
    "count_all_resources": ToolRisk.READ,
    "collect_resources_summary": ToolRisk.READ,
    # resource groups
    "create_resource_group": ToolRisk.WRITE,
    "update_resource_group": ToolRisk.WRITE,
    "show_resource_group": ToolRisk.READ,
    "list_resource_groups": ToolRisk.READ,
    "add_resources_to_group": ToolRisk.WRITE,
    "remove_resource_from_group": ToolRisk.WRITE,
    "delete_resource_group": ToolRisk.DANGEROUS,
    # resource relations
    "show_resource_relations": ToolRisk.READ,
    # advanced queries
    "create_stored_query": ToolRisk.WRITE,
    "list_stored_queries": ToolRisk.READ,
    "show_stored_query": ToolRisk.READ,
    "update_stored_query": ToolRisk.WRITE,
    "delete_stored_query": ToolRisk.DANGEROUS,
}

_DANGEROUS_TOOLS = {"delete_resource_group", "delete_stored_query"}


def test_all_tools_declare_risk() -> None:
    for tool_name, risk in _ALL_TOOLS.items():
        assert get_tool_risk(tool_name) is risk, tool_name


def test_dangerous_tools_have_confirm_parameter() -> None:
    for tool_name in _DANGEROUS_TOOLS:
        assert tool_supports_confirm(tool_name), tool_name
    for tool_name, risk in _ALL_TOOLS.items():
        if risk is not ToolRisk.DANGEROUS:
            assert not tool_supports_confirm(tool_name), tool_name


async def test_tools_are_registered_on_server() -> None:
    from mcp_server_rc.server import mcp

    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert tool_names == set(_ALL_TOOLS)


class StubService:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def _record(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.payload

    async def run_query(self, *, expression: str, limit: int = 50) -> dict[str, Any]:
        return self._record(expression=expression, limit=limit)

    async def list_providers(
        self, *, offset: int | None = None, limit: int | None = None, x_language: str | None = None
    ) -> dict[str, Any]:
        return self._record(offset=offset, limit=limit, x_language=x_language)

    async def list_all_resources(self, **kwargs: Any) -> dict[str, Any]:
        return self._record(**kwargs)

    async def show_resource_detail(self, *, resource_id: str) -> dict[str, Any]:
        return self._record(resource_id=resource_id)

    async def list_all_tags(self, **kwargs: Any) -> dict[str, Any]:
        return self._record(**kwargs)

    async def count_all_resources(self, **kwargs: Any) -> dict[str, Any]:
        return self._record(**kwargs)

    async def collect_resources_summary(self, **kwargs: Any) -> dict[str, Any]:
        return self._record(**kwargs)

    async def create_resource_group(
        self, *, group_name: str, description: str | None = None
    ) -> dict[str, Any]:
        return self._record(group_name=group_name, description=description)

    async def delete_resource_group(
        self, *, group_id: str, confirm: bool = False
    ) -> dict[str, Any]:
        return self._record(group_id=group_id, confirm=confirm)

    async def update_resource_group(
        self, *, group_id: str, description: str | None = None
    ) -> dict[str, Any]:
        return self._record(group_id=group_id, description=description)

    async def show_resource_group(self, *, group_id: str) -> dict[str, Any]:
        return self._record(group_id=group_id)

    async def list_resource_groups(self, **kwargs: Any) -> dict[str, Any]:
        return self._record(**kwargs)

    async def add_resources_to_group(
        self, *, group_id: str, resource_ids: list[str]
    ) -> dict[str, Any]:
        return self._record(group_id=group_id, resource_ids=resource_ids)

    async def remove_resource_from_group(
        self, *, group_id: str, resource_id: str
    ) -> dict[str, Any]:
        return self._record(group_id=group_id, resource_id=resource_id)

    async def show_resource_relations(self, **kwargs: Any) -> dict[str, Any]:
        return self._record(**kwargs)

    async def create_stored_query(
        self, *, name: str, expression: str, description: str | None = None
    ) -> dict[str, Any]:
        return self._record(name=name, expression=expression, description=description)

    async def list_stored_queries(self, **kwargs: Any) -> dict[str, Any]:
        return self._record(**kwargs)

    async def show_stored_query(self, *, query_id: str) -> dict[str, Any]:
        return self._record(query_id=query_id)

    async def update_stored_query(
        self, *, query_id: str, name: str, expression: str, description: str | None = None
    ) -> dict[str, Any]:
        return self._record(
            query_id=query_id, name=name, expression=expression, description=description
        )

    async def delete_stored_query(self, *, query_id: str, confirm: bool = False) -> dict[str, Any]:
        return self._record(query_id=query_id, confirm=confirm)


@pytest.fixture
def stub_service(monkeypatch: pytest.MonkeyPatch) -> StubService:
    stub = StubService({"items": [], "count": 0, "total": 0})
    monkeypatch.setattr("mcp_server_rc.tools.resource.ResourceService", lambda: stub)
    return stub


async def test_run_query_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import run_query

    result = await run_query(expression="SELECT * FROM resources", limit=5)
    assert result == {"items": [], "count": 0, "total": 0}
    assert stub_service.calls == [{"expression": "SELECT * FROM resources", "limit": 5}]


async def test_run_query_tool_limit_defaults_to_50(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import run_query

    await run_query(expression="SELECT * FROM resources")
    assert stub_service.calls == [{"expression": "SELECT * FROM resources", "limit": 50}]


async def test_list_providers_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import list_providers

    await list_providers(offset=10, limit=50, x_language="zh-cn")
    assert stub_service.calls == [{"offset": 10, "limit": 50, "x_language": "zh-cn"}]


async def test_list_providers_tool_defaults_none(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import list_providers

    await list_providers()
    assert stub_service.calls == [{"offset": None, "limit": None, "x_language": None}]


async def test_list_all_resources_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import list_all_resources

    await list_all_resources(
        region_id="cn-north-4", resource_type="ecs.cloudservers", limit=5, name="web"
    )
    assert stub_service.calls[0]["region_id"] == "cn-north-4"
    assert stub_service.calls[0]["resource_type"] == "ecs.cloudservers"
    assert stub_service.calls[0]["limit"] == 5
    assert stub_service.calls[0]["name"] == "web"
    assert stub_service.calls[0]["marker"] is None


async def test_show_resource_detail_tool_passes_resource_id(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import show_resource_detail

    await show_resource_detail(resource_id="r-1")
    assert stub_service.calls == [{"resource_id": "r-1"}]


async def test_list_all_tags_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import list_all_tags

    await list_all_tags(key="env", limit=10)
    assert stub_service.calls[0]["key"] == "env"
    assert stub_service.calls[0]["limit"] == 10


async def test_count_all_resources_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import count_all_resources

    await count_all_resources(
        resource_id="r-1",
        name="web",
        group_id="g-1",
        resource_type=["ecs.cloudservers"],
        region_id=["cn-north-4"],
    )
    assert stub_service.calls[0]["id_"] == "r-1"
    assert stub_service.calls[0]["name"] == "web"
    assert stub_service.calls[0]["group_id"] == "g-1"
    assert stub_service.calls[0]["resource_type"] == ["ecs.cloudservers"]
    assert stub_service.calls[0]["region_id"] == ["cn-north-4"]


async def test_collect_resources_summary_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import collect_resources_summary

    await collect_resources_summary(name="web")
    assert stub_service.calls[0]["name"] == "web"


async def test_create_resource_group_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import create_resource_group

    await create_resource_group(group_name="web-grp", description="d")
    assert stub_service.calls == [{"group_name": "web-grp", "description": "d"}]


async def test_delete_resource_group_tool_passes_confirm(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import delete_resource_group

    await delete_resource_group(group_id="g-1", confirm=True)
    assert stub_service.calls == [{"group_id": "g-1", "confirm": True}]


async def test_update_resource_group_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import update_resource_group

    await update_resource_group(group_id="g-1", description="d")
    assert stub_service.calls == [{"group_id": "g-1", "description": "d"}]


async def test_show_resource_group_tool_passes_group_id(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import show_resource_group

    await show_resource_group(group_id="g-1")
    assert stub_service.calls == [{"group_id": "g-1"}]


async def test_list_resource_groups_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import list_resource_groups

    await list_resource_groups(limit=5)
    assert stub_service.calls[0]["limit"] == 5


async def test_add_resources_to_group_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import add_resources_to_group

    await add_resources_to_group(group_id="g-1", resource_ids=["r-1", "r-2"])
    assert stub_service.calls == [{"group_id": "g-1", "resource_ids": ["r-1", "r-2"]}]


async def test_remove_resource_from_group_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import remove_resource_from_group

    await remove_resource_from_group(group_id="g-1", resource_id="r-1")
    assert stub_service.calls == [{"group_id": "g-1", "resource_id": "r-1"}]


async def test_show_resource_relations_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import show_resource_relations

    await show_resource_relations(resource_id="r-1", limit=5)
    assert stub_service.calls[0]["resource_id"] == "r-1"
    assert stub_service.calls[0]["limit"] == 5


async def test_create_stored_query_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import create_stored_query

    await create_stored_query(name="q1", expression="SELECT 1", description="d")
    assert stub_service.calls == [{"name": "q1", "expression": "SELECT 1", "description": "d"}]


async def test_list_stored_queries_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import list_stored_queries

    await list_stored_queries(limit=5, name="q1")
    assert stub_service.calls[0]["limit"] == 5
    assert stub_service.calls[0]["name"] == "q1"


async def test_show_stored_query_tool_passes_query_id(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import show_stored_query

    await show_stored_query(query_id="q-1")
    assert stub_service.calls == [{"query_id": "q-1"}]


async def test_update_stored_query_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import update_stored_query

    await update_stored_query(query_id="q-1", name="q2", expression="SELECT 2")
    assert stub_service.calls == [
        {"query_id": "q-1", "name": "q2", "expression": "SELECT 2", "description": None}
    ]


async def test_delete_stored_query_tool_passes_confirm(stub_service: StubService) -> None:
    from mcp_server_rc.tools.resource import delete_stored_query

    await delete_stored_query(query_id="q-1", confirm=True)
    assert stub_service.calls == [{"query_id": "q-1", "confirm": True}]


async def test_tool_error_becomes_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    from huaweicloud_mcp_core.errors import McpToolError

    class FailingService(StubService):
        async def show_resource_detail(self, *, resource_id: str) -> dict[str, Any]:
            raise McpToolError("MCP_NOT_FOUND", f"resource '{resource_id}' not found.")

    monkeypatch.setattr("mcp_server_rc.tools.resource.ResourceService", lambda: FailingService({}))
    from mcp_server_rc.tools.resource import show_resource_detail

    result = await show_resource_detail(resource_id="ghost")
    assert result["error"]["code"] == "MCP_NOT_FOUND"


def test_main_entrypoint_calls_run_standard(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def fake_run_standard(server: Any, service_name: str) -> None:
        called.append(service_name)

    monkeypatch.setattr("huaweicloud_mcp_core.server.run_standard", fake_run_standard)
    from mcp_server_rc.main import main

    main()
    assert called == ["rc"]
