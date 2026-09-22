# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Environment-based configuration for Huawei Cloud MCP servers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from huaweicloud_mcp_core.errors import McpToolError

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def _env_csv(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class McpSettings:
    """Immutable snapshot of all environment configuration."""

    access_key: str = ""
    secret_key: str = ""
    region: str = ""
    project_id: str | None = None
    security_token: str | None = None
    endpoint: str | None = None
    read_only: bool = False
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    protected_ids: tuple[str, ...] = ()
    protected_names: tuple[str, ...] = ()
    protected_tags: tuple[str, ...] = ()
    guardrails_config_path: str | None = None
    audit_file: str | None = None

    @classmethod
    def from_env(cls, *, require_credentials: bool = True) -> McpSettings:
        missing = [
            name
            for name, value in (
                ("HUAWEICLOUD_ACCESS_KEY", os.getenv("HUAWEICLOUD_ACCESS_KEY")),
                ("HUAWEICLOUD_SECRET_KEY", os.getenv("HUAWEICLOUD_SECRET_KEY")),
                ("HUAWEICLOUD_REGION", os.getenv("HUAWEICLOUD_REGION")),
            )
            if not value
        ]
        if missing and require_credentials:
            raise McpToolError(
                code="MCP_INVALID_ARGS",
                message=f"Missing required environment variables: {', '.join(missing)}.",
                hint=(
                    "Export HUAWEICLOUD_ACCESS_KEY, HUAWEICLOUD_SECRET_KEY and "
                    "HUAWEICLOUD_REGION (see the Configuration section of the README)."
                ),
            )
        return cls(
            access_key=os.getenv("HUAWEICLOUD_ACCESS_KEY", ""),
            secret_key=os.getenv("HUAWEICLOUD_SECRET_KEY", ""),
            region=os.getenv("HUAWEICLOUD_REGION", ""),
            project_id=os.getenv("HUAWEICLOUD_PROJECT_ID") or None,
            security_token=os.getenv("HUAWEICLOUD_SECURITY_TOKEN") or None,
            endpoint=os.getenv("HUAWEICLOUD_ENDPOINT") or None,
            read_only=_env_bool("HUAWEICLOUD_MCP_READ_ONLY"),
            server_host=os.getenv("MCP_SERVER_HOST", "0.0.0.0"),
            server_port=_env_int("MCP_SERVER_PORT", 8000),
            protected_ids=_env_csv("HUAWEICLOUD_MCP_PROTECTED_IDS"),
            protected_names=_env_csv("HUAWEICLOUD_MCP_PROTECTED_NAMES"),
            protected_tags=_env_csv("HUAWEICLOUD_MCP_PROTECTED_TAGS"),
            guardrails_config_path=os.getenv("HUAWEICLOUD_MCP_GUARDRAILS_CONFIG") or None,
            audit_file=os.getenv("HUAWEICLOUD_MCP_AUDIT_FILE") or None,
        )
