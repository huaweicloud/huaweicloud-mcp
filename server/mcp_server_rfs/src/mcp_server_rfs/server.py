# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""FastMCP instance construction for the RFS server (guardrails auto-installed)."""

from huaweicloud_mcp_core.server import build_server

mcp = build_server("rfs")

from mcp_server_rfs.tools import stack  # noqa: E402,F401
