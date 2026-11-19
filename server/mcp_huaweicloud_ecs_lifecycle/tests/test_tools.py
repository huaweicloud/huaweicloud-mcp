# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the ECS lifecycle tool layer: registration, risk, confirm protocol."""

from __future__ import annotations

from typing import Any

import pytest
from huaweicloud_mcp_core.security import ToolRisk, get_tool_risk

import mcp_huaweicloud_ecs_lifecycle.server  # noqa: F401  (import registers all tools)

_TOOL_NAMES = {
    "list_servers",
    "show_server",
    "show_job",
    "list_images",
    "list_flavors",
    "list_keypairs",
    "create_server",
    "create_on_demand_server",
    "update_server",
    "delete_servers",
}

_READ_TOOLS = {
    "list_servers",
    "show_server",
    "show_job",
    "list_images",
    "list_flavors",
    "list_keypairs",
}
_WRITE_TOOLS = {"update_server", "create_server", "create_on_demand_server"}
_DANGEROUS_TOOLS = {"delete_servers"}

# Every tool that can change cloud state must follow the two-call confirm protocol.
_MUTATING_TOOLS = _WRITE_TOOLS | _DANGEROUS_TOOLS


def test_tool_risk_declarations() -> None:
    for tool_name in _READ_TOOLS:
        assert get_tool_risk(tool_name) is ToolRisk.READ, tool_name
    for tool_name in _WRITE_TOOLS:
        assert get_tool_risk(tool_name) is ToolRisk.WRITE, tool_name
    for tool_name in _DANGEROUS_TOOLS:
        assert get_tool_risk(tool_name) is ToolRisk.DANGEROUS, tool_name


async def test_tools_are_registered_on_server() -> None:
    from mcp_huaweicloud_ecs_lifecycle.server import mcp

    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert tool_names == _TOOL_NAMES


async def test_mutating_tools_expose_confirm_parameter_defaulting_to_false() -> None:
    from mcp_huaweicloud_ecs_lifecycle.server import mcp

    tools = {tool.name: tool for tool in await mcp.list_tools()}
    for name in _MUTATING_TOOLS:
        schema = tools[name].input_schema
        assert "confirm" in schema["properties"], f"{name} lacks the confirm parameter"
        assert "confirm" not in schema.get("required", []), (
            f"{name} must not force confirm to be provided"
        )
    for name in _READ_TOOLS:
        assert "confirm" not in tools[name].input_schema["properties"], name


class StubService:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    async def list_servers(
        self,
        *,
        name: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        self.calls.append({"name": name, "status": status, "limit": limit})
        return self.payload

    async def show_server(self, server_id: str) -> dict[str, Any]:
        self.calls.append({"server_id": server_id})
        return self.payload

    async def show_job(self, job_id: str) -> dict[str, Any]:
        self.calls.append({"job_id": job_id})
        return self.payload

    async def list_images(
        self,
        *,
        name: str | None = None,
        os_type: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        self.calls.append({"name": name, "os_type": os_type, "limit": limit})
        return self.payload

    async def list_flavors(
        self,
        *,
        vcpus: int | None = None,
        ram_gb: int | None = None,
        flavor_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        self.calls.append(
            {"vcpus": vcpus, "ram_gb": ram_gb, "flavor_id": flavor_id, "limit": limit}
        )
        return self.payload

    async def list_keypairs(self, *, limit: int = 20) -> dict[str, Any]:
        self.calls.append({"limit": limit})
        return self.payload

    async def create_server(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.payload

    async def create_on_demand_server(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.payload

    async def update_server(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.payload

    async def delete_servers(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.payload


@pytest.fixture
def stub_service(monkeypatch: pytest.MonkeyPatch) -> StubService:
    stub = StubService({"ok": True})
    # Discovery tools bind EcsLifecycleService in their own module, so both
    # tool modules need the stub patched in.
    monkeypatch.setattr(
        "mcp_huaweicloud_ecs_lifecycle.tools.lifecycle.EcsLifecycleService", lambda: stub
    )
    monkeypatch.setattr(
        "mcp_huaweicloud_ecs_lifecycle.tools.discovery.EcsLifecycleService", lambda: stub
    )
    return stub


async def test_list_servers_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_huaweicloud_ecs_lifecycle.tools.lifecycle import list_servers

    result = await list_servers(name="web", status="ACTIVE", limit=5)
    assert result == {"ok": True}
    assert stub_service.calls == [{"name": "web", "status": "ACTIVE", "limit": 5}]


async def test_read_tools_forward_identifiers(stub_service: StubService) -> None:
    from mcp_huaweicloud_ecs_lifecycle.tools.lifecycle import show_job, show_server

    await show_server("srv-1")
    await show_job("job-1")
    assert stub_service.calls == [{"server_id": "srv-1"}, {"job_id": "job-1"}]


async def test_discovery_tools_forward_filters(stub_service: StubService) -> None:
    from mcp_huaweicloud_ecs_lifecycle.tools.discovery import (
        list_flavors,
        list_images,
        list_keypairs,
    )

    await list_images(name="Ubuntu", os_type="Linux", limit=10)
    await list_flavors(vcpus=1, ram_gb=1, flavor_id="x1.1u.1g", limit=10)
    await list_keypairs(limit=10)

    assert stub_service.calls == [
        {"name": "Ubuntu", "os_type": "Linux", "limit": 10},
        {"vcpus": 1, "ram_gb": 1, "flavor_id": "x1.1u.1g", "limit": 10},
        {"limit": 10},
    ]


async def test_delete_servers_tool_forwards_confirm(stub_service: StubService) -> None:
    from mcp_huaweicloud_ecs_lifecycle.tools.lifecycle import delete_servers

    await delete_servers(server_ids=["srv-1"], delete_volume=True, confirm=True)

    assert stub_service.calls == [
        {
            "server_ids": ["srv-1"],
            "delete_volume": True,
            "delete_publicip": False,
            "confirm": True,
        }
    ]


async def test_update_server_tool_forwards_confirm(stub_service: StubService) -> None:
    from mcp_huaweicloud_ecs_lifecycle.tools.lifecycle import update_server

    await update_server(server_id="srv-1", name="web-2", confirm=True)

    assert stub_service.calls == [
        {
            "server_id": "srv-1",
            "name": "web-2",
            "description": None,
            "hostname": None,
            "confirm": True,
        }
    ]


async def test_create_server_tool_forwards_confirm(stub_service: StubService) -> None:
    from mcp_huaweicloud_ecs_lifecycle.tools.lifecycle import create_server

    await create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="GPSSD",
        confirm=False,
    )

    call = stub_service.calls[0]
    assert call["confirm"] is False
    assert call["name"] == "web"
    assert call["root_volume_type"] == "GPSSD"


async def test_tool_error_becomes_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    from huaweicloud_mcp_core.errors import McpToolError

    class FailingService(StubService):
        async def show_server(self, server_id: str) -> dict[str, Any]:
            raise McpToolError("MCP_NOT_FOUND", "Server srv-1 not found in this region.")

    monkeypatch.setattr(
        "mcp_huaweicloud_ecs_lifecycle.tools.lifecycle.EcsLifecycleService",
        lambda: FailingService({}),
    )
    from mcp_huaweicloud_ecs_lifecycle.tools.lifecycle import show_server

    result = await show_server("srv-1")
    assert result["error"]["code"] == "MCP_NOT_FOUND"
