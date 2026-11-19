# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""MCPServer instance construction for the ECS lifecycle server (guardrails auto-installed)."""

from huaweicloud_mcp_core.server import build_server

mcp = build_server("ecs-lifecycle")

from mcp_huaweicloud_ecs_lifecycle.tools import (  # noqa: E402,F401
    discovery,
    lifecycle,
)
