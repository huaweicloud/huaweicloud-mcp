# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the ECS tool layer: registration, guard declaration, invocation."""

from __future__ import annotations

from typing import Any

import pytest
from huaweicloud_mcp_core.security import ToolRisk, get_tool_risk

import mcp_huaweicloud_ecs_readonly.server  # noqa: F401  (import registers all tools)

_TOOL_NAMES = {
    "list_servers",
    "count_servers",
    "count_servers_by_status",
    "list_server_flavors",
    "analyze_server_resources",
    "analyze_server_ips",
}


def test_all_tools_declare_read_risk() -> None:
    for tool_name in _TOOL_NAMES:
        assert get_tool_risk(tool_name) is ToolRisk.READ, tool_name


async def test_tools_are_registered_on_server() -> None:
    from mcp_huaweicloud_ecs_readonly.server import mcp

    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert tool_names == _TOOL_NAMES


class StubService:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    async def list_servers(
        self,
        *,
        name: str | None = None,
        status: str | None = None,
        flavor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        self.calls.append({"name": name, "status": status, "flavor": flavor, "limit": limit})
        return self.payload

    async def count_servers(self) -> dict[str, Any]:
        self.calls.append({})
        return self.payload

    async def count_servers_by_status(self) -> dict[str, Any]:
        self.calls.append({})
        return self.payload

    async def list_server_flavors(self) -> dict[str, Any]:
        self.calls.append({})
        return self.payload

    async def analyze_server_resources(self) -> dict[str, Any]:
        self.calls.append({})
        return self.payload

    async def analyze_server_ips(self) -> dict[str, Any]:
        self.calls.append({})
        return self.payload


@pytest.fixture
def stub_service(monkeypatch: pytest.MonkeyPatch) -> StubService:
    stub = StubService({"count": 0})
    monkeypatch.setattr("mcp_huaweicloud_ecs_readonly.tools.ecs.EcsService", lambda: stub)
    return stub


async def test_list_servers_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_huaweicloud_ecs_readonly.tools.ecs import list_servers

    result = await list_servers(name="web", status="ACTIVE", flavor="c7", limit=5)
    assert result == {"count": 0}
    assert stub_service.calls == [{"name": "web", "status": "ACTIVE", "flavor": "c7", "limit": 5}]


async def test_analyze_tools_forward_without_arguments(stub_service: StubService) -> None:
    from mcp_huaweicloud_ecs_readonly.tools.ecs import (
        analyze_server_ips,
        analyze_server_resources,
        count_servers,
        count_servers_by_status,
        list_server_flavors,
    )

    await count_servers()
    await count_servers_by_status()
    await list_server_flavors()
    await analyze_server_resources()
    await analyze_server_ips()
    assert len(stub_service.calls) == 5


async def test_tool_error_becomes_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    from huaweicloud_mcp_core.errors import McpToolError

    class FailingService(StubService):
        async def count_servers(self) -> dict[str, Any]:
            raise McpToolError("MCP_SDK_ERROR", "ECS is down.")

    monkeypatch.setattr("mcp_huaweicloud_ecs_readonly.tools.ecs.EcsService", lambda: FailingService({}))
    from mcp_huaweicloud_ecs_readonly.tools.ecs import count_servers

    result = await count_servers()
    assert result["error"]["code"] == "MCP_SDK_ERROR"
