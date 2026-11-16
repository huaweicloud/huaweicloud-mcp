# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""MCPServer instance construction for the ECS server (guardrails auto-installed)."""

from huaweicloud_mcp_core.server import build_server

mcp = build_server("ecs")

from mcp_server_ecs_readonly.tools import ecs  # noqa: E402,F401
