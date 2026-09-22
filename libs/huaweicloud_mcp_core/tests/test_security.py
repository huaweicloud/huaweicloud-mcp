# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the @guard decorator and risk registry."""

from __future__ import annotations

from typing import Any

import pytest

from huaweicloud_mcp_core.errors import McpToolError
from huaweicloud_mcp_core.security import (
    ToolRisk,
    get_tool_risk,
    guard,
    reset_registries,
    tool_supports_confirm,
)


@guard(risk=ToolRisk.WRITE)
async def update_widget(widget_id: str, name: str | None = None) -> dict[str, Any]:
    return {"widget_id": widget_id, "name": name}


@guard(risk=ToolRisk.DANGEROUS)
async def delete_widget(widget_id: str, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        return {"confirmation_required": True}
    return {"deleted": True}


@guard(risk=ToolRisk.READ)
async def failing_reader() -> dict[str, Any]:
    raise McpToolError("MCP_NOT_FOUND", "nope", hint="try again")


def test_guard_registers_risk() -> None:
    assert get_tool_risk("update_widget") is ToolRisk.WRITE
    assert get_tool_risk("delete_widget") is ToolRisk.DANGEROUS
    assert get_tool_risk("failing_reader") is ToolRisk.READ
    assert get_tool_risk("never_registered") is None


def test_confirm_parameter_detection() -> None:
    assert tool_supports_confirm("delete_widget") is True
    assert tool_supports_confirm("update_widget") is False


@pytest.mark.asyncio
async def test_wrapper_converts_tool_error() -> None:
    result = await failing_reader()
    assert result["error"]["code"] == "MCP_NOT_FOUND"
    assert result["error"]["hint"] == "try again"


@pytest.mark.asyncio
async def test_wrapper_passes_through_success() -> None:
    result = await update_widget("w-1", name="prod")
    assert result == {"widget_id": "w-1", "name": "prod"}


def test_reset_registries() -> None:
    reset_registries()
    assert get_tool_risk("update_widget") is None
    assert tool_supports_confirm("delete_widget") is False
