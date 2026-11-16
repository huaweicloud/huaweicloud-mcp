# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tool risk declaration and the @guard decorator."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, TypeVar

from huaweicloud_mcp_core.errors import McpToolError


class ToolRisk(Enum):
    READ = "READ"
    WRITE = "WRITE"
    DANGEROUS = "DANGEROUS"


_TOOL_RISK_REGISTRY: dict[str, ToolRisk] = {}
_TOOLS_WITH_CONFIRM: set[str] = set()

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def guard(*, risk: ToolRisk) -> Callable[[F], F]:
    """Declare a tool's risk level and convert McpToolError to the error envelope."""

    def decorator(fn: F) -> F:
        signature = inspect.signature(fn)
        if "confirm" in signature.parameters:
            _TOOLS_WITH_CONFIRM.add(fn.__name__)

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except McpToolError as exc:
                return exc.to_dict()

        _TOOL_RISK_REGISTRY[fn.__name__] = risk
        wrapper.__tool_risk__ = risk  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def get_tool_risk(tool_name: str) -> ToolRisk | None:
    return _TOOL_RISK_REGISTRY.get(tool_name)


def tool_supports_confirm(tool_name: str) -> bool:
    return tool_name in _TOOLS_WITH_CONFIRM


def reset_registries() -> None:
    _TOOL_RISK_REGISTRY.clear()
    _TOOLS_WITH_CONFIRM.clear()
