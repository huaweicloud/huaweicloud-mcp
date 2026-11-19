# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Test-support helpers shared by the ECS server packages.

These are used by ``conftest.py`` fixtures across the ecs and ecs-lifecycle
packages so the two do not duplicate env-cleaning and server-registration
boilerplate. They are NOT part of the runtime API; do not import from
``huaweicloud_mcp_ecs_common`` itself.
"""

from __future__ import annotations

from typing import Any

_ENV_KEYS = [
    "HUAWEICLOUD_ACCESS_KEY",
    "HUAWEICLOUD_SECRET_KEY",
    "HUAWEICLOUD_REGION",
    "HUAWEICLOUD_PROJECT_ID",
    "HUAWEICLOUD_SECURITY_TOKEN",
    "HUAWEICLOUD_ENDPOINT",
    "HUAWEICLOUD_MCP_SKIP_SSL_VERIFY_REGIONS",
    "HUAWEICLOUD_MCP_MAX_CONCURRENT",
    "HUAWEICLOUD_MCP_READ_ONLY",
    "HUAWEICLOUD_MCP_PROTECTED_IDS",
    "HUAWEICLOUD_MCP_PROTECTED_NAMES",
    "HUAWEICLOUD_MCP_PROTECTED_TAGS",
    "HUAWEICLOUD_MCP_GUARDRAILS_CONFIG",
    "HUAWEICLOUD_MCP_AUDIT_FILE",
    "MCP_SERVER_PORT",
    "MCP_SERVER_HOST",
]


def register_server(
    client: Any,
    server_id: str,
    name: str | None = None,
    status: str = "ACTIVE",
    **extra: Any,
) -> dict[str, Any]:
    """Append one ECS server record (real-SDK-shaped) to a fake client."""
    server: dict[str, Any] = {
        "id": server_id,
        "name": name or server_id,
        "status": status,
        # ram matches the real SDK unit (MB): c7.large.2 = 4096MB
        "flavor": {"id": "c7.large.2", "name": "c7.large.2", "vcpus": 2, "ram": 4096},
        "addresses": {},
        "tags": [],
        "created": "2026-01-01T00:00:00Z",
    }
    server.update(extra)
    client.servers.append(server)
    return server
