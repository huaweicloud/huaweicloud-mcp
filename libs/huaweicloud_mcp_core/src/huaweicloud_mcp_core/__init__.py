# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Shared core library for Huawei Cloud MCP servers."""

from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.credentials import CredentialScope, build_credentials
from huaweicloud_mcp_core.errors import McpToolError, wrap_sdk_error
from huaweicloud_mcp_core.output import page_result, single_result
from huaweicloud_mcp_core.security import ToolRisk, guard
from huaweicloud_mcp_core.server import build_server, run_standard

__all__ = [
    "CredentialScope",
    "McpSettings",
    "McpToolError",
    "ToolRisk",
    "build_credentials",
    "build_server",
    "guard",
    "page_result",
    "run_standard",
    "single_result",
    "wrap_sdk_error",
]
