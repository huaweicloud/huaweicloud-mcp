# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the RFS tool layer: registration, guard declaration, invocation."""

from __future__ import annotations

from typing import Any

import pytest

from huaweicloud_mcp_core.security import ToolRisk, get_tool_risk, tool_supports_confirm

import mcp_server_rfs.server  # noqa: F401  (import registers all tools)


def test_all_six_tools_declare_risk() -> None:
    expected = {
        "list_stacks": ToolRisk.READ,
        "get_stack": ToolRisk.READ,
        "preview_stack_changes": ToolRisk.READ,
        "deploy_stack": ToolRisk.WRITE,
        "diagnose_stack": ToolRisk.READ,
        "delete_stack": ToolRisk.DANGEROUS,
    }
    for tool_name, risk in expected.items():
        assert get_tool_risk(tool_name) is risk, tool_name


def test_dangerous_tool_has_confirm_parameter() -> None:
    assert tool_supports_confirm("delete_stack") is True
    assert tool_supports_confirm("deploy_stack") is False


async def test_tools_are_registered_on_server() -> None:
    from mcp_server_rfs.server import mcp

    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert tool_names == {
        "list_stacks",
        "get_stack",
        "preview_stack_changes",
        "deploy_stack",
        "diagnose_stack",
        "delete_stack",
    }


class StubService:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    async def list_stacks(
        self,
        *,
        name: str | None = None,
        limit: int = 20,
        marker: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"name": name, "limit": limit, "marker": marker})
        return self.payload

    async def get_stack(self, *, stack_name: str) -> dict[str, Any]:
        self.calls.append({"stack_name": stack_name})
        return self.payload

    async def preview_stack_changes(
        self,
        *,
        stack_name: str,
        template: str | None = None,
        template_uri: str | None = None,
        variables: dict[str, str] | None = None,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        self.calls.append({"stack_name": stack_name, "template": template})
        return self.payload

    async def deploy_stack(
        self,
        *,
        stack_name: str,
        template: str | None = None,
        template_uri: str | None = None,
        variables: dict[str, str] | None = None,
        enable_deletion_protection: bool = False,
        wait: bool = False,
        timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "stack_name": stack_name,
                "template": template,
                "wait": wait,
                "enable_deletion_protection": enable_deletion_protection,
            }
        )
        return self.payload

    async def diagnose_stack(
        self,
        *,
        stack_name: str,
        event_limit: int = 20,
    ) -> dict[str, Any]:
        self.calls.append({"stack_name": stack_name, "event_limit": event_limit})
        return self.payload

    async def delete_stack(
        self,
        *,
        stack_name: str,
        retain_resources: bool = False,
        confirm: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(
            {"stack_name": stack_name, "retain_resources": retain_resources, "confirm": confirm}
        )
        return self.payload


@pytest.fixture
def stub_service(monkeypatch: pytest.MonkeyPatch) -> StubService:
    stub = StubService({"items": [], "count": 0})
    monkeypatch.setattr("mcp_server_rfs.tools.stack.StackService", lambda: stub)
    return stub


async def test_list_stacks_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rfs.tools.stack import list_stacks

    result = await list_stacks(name="web", limit=5)
    assert result == {"items": [], "count": 0}
    assert stub_service.calls == [{"name": "web", "limit": 5, "marker": None}]


async def test_deploy_tool_passes_arguments(stub_service: StubService) -> None:
    from mcp_server_rfs.tools.stack import deploy_stack

    await deploy_stack(stack_name="web", template="tpl", wait=True)
    assert stub_service.calls == [
        {
            "stack_name": "web",
            "template": "tpl",
            "wait": True,
            "enable_deletion_protection": False,
        }
    ]


async def test_delete_tool_passes_confirm(stub_service: StubService) -> None:
    from mcp_server_rfs.tools.stack import delete_stack

    await delete_stack(stack_name="web", retain_resources=True, confirm=True)
    assert stub_service.calls == [
        {"stack_name": "web", "retain_resources": True, "confirm": True}
    ]


async def test_diagnose_tool_passes_event_limit(stub_service: StubService) -> None:
    from mcp_server_rfs.tools.stack import diagnose_stack

    await diagnose_stack(stack_name="web", event_limit=50)
    assert stub_service.calls == [{"stack_name": "web", "event_limit": 50}]


async def test_tool_error_becomes_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    from huaweicloud_mcp_core.errors import McpToolError

    class FailingService(StubService):
        async def get_stack(self, *, stack_name: str) -> dict[str, Any]:
            raise McpToolError("MCP_NOT_FOUND", f"Stack '{stack_name}' not found.")

    monkeypatch.setattr("mcp_server_rfs.tools.stack.StackService", lambda: FailingService({}))
    from mcp_server_rfs.tools.stack import get_stack

    result = await get_stack("ghost")
    assert result["error"]["code"] == "MCP_NOT_FOUND"
