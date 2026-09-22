# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Unified error model for Huawei Cloud MCP tools."""

from __future__ import annotations

from typing import Any

_INTERNAL_CODES = {
    "MCP_INVALID_ARGS",
    "MCP_NOT_FOUND",
    "MCP_PERMISSION_DENIED",
    "MCP_READ_ONLY",
    "MCP_GUARDRAIL_BLOCKED",
    "MCP_GUARDRAIL_ERROR",
    "MCP_SDK_ERROR",
    "MCP_PROJECT_NOT_FOUND",
}


class McpToolError(Exception):
    """The only business exception tools are allowed to raise."""

    def __init__(
        self,
        code: str,
        message: str,
        request_id: str | None = None,
        doc_url: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id
        self.doc_url = doc_url
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.request_id:
            error["request_id"] = self.request_id
        if self.doc_url:
            error["doc_url"] = self.doc_url
        error["hint"] = self.hint or "Inspect the error message and adjust the tool call."
        return {"error": error}


def wrap_sdk_error(exc: Exception) -> McpToolError:
    """Convert huaweicloudsdk exceptions into McpToolError with full context."""
    try:
        from huaweicloudsdkcore.exceptions.exceptions import (
            ClientRequestException,
            ServiceResponseException,
        )
    except ImportError:
        return McpToolError("MCP_SDK_ERROR", str(exc))

    if isinstance(exc, ServiceResponseException):
        return McpToolError(
            code=getattr(exc, "error_code", None) or f"HTTP_{exc.status_code}",
            message=str(getattr(exc, "error_msg", None) or exc),
            request_id=getattr(exc, "request_id", None),
        )
    if isinstance(exc, ClientRequestException):
        return McpToolError(
            code=f"HTTP_{exc.status_code}",
            message=str(exc),
            request_id=getattr(exc, "request_id", None),
        )
    return McpToolError("MCP_SDK_ERROR", str(exc))
