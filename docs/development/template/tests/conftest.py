# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Shared fixtures for the PLACEHOLDER server tests."""

from __future__ import annotations

from typing import Any

import pytest

_ENV_KEYS = [
    "HUAWEICLOUD_ACCESS_KEY",
    "HUAWEICLOUD_SECRET_KEY",
    "HUAWEICLOUD_REGION",
    "HUAWEICLOUD_PROJECT_ID",
    "HUAWEICLOUD_SECURITY_TOKEN",
    "HUAWEICLOUD_ENDPOINT",
    "HUAWEICLOUD_MCP_READ_ONLY",
    "HUAWEICLOUD_MCP_PROTECTED_IDS",
    "HUAWEICLOUD_MCP_PROTECTED_NAMES",
    "HUAWEICLOUD_MCP_PROTECTED_TAGS",
    "HUAWEICLOUD_MCP_GUARDRAILS_CONFIG",
    "HUAWEICLOUD_MCP_AUDIT_FILE",
    "MCP_SERVER_PORT",
    "MCP_SERVER_HOST",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class FakePlaceholderClient:
    """In-memory fake of the PlaceholderClient interface used by service tests."""

    def __init__(self) -> None:
        self.resources: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_resources(self, *, limit: int, marker: str | None) -> dict[str, Any]:
        self.calls.append(("list_resources", {"limit": limit, "marker": marker}))
        return {"resources": list(self.resources.values())[:limit]}

    async def get_resource(self, resource_id: str) -> dict[str, Any] | None:
        self.calls.append(("get_resource", {"resource_id": resource_id}))
        return self.resources.get(resource_id)

    async def delete_resource(self, *, resource_id: str) -> dict[str, Any]:
        self.calls.append(("delete_resource", {"resource_id": resource_id}))
        self.resources.pop(resource_id, None)
        return {}


@pytest.fixture
def fake_client() -> FakePlaceholderClient:
    return FakePlaceholderClient()


def register_resource(
    client: FakePlaceholderClient,
    resource_id: str,
    name: str | None = None,
    status: str = "ACTIVE",
    **extra: Any,
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "id": resource_id,
        "name": name or resource_id,
        "status": status,
        "tags": {},
    }
    resource.update(extra)
    client.resources[resource_id] = resource
    return resource
