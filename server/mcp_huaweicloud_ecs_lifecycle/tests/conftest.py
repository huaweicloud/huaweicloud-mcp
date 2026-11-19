# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Shared fixtures for the ecs-lifecycle server tests."""

from __future__ import annotations

from typing import Any

import pytest
from huaweicloud_mcp_ecs_common.testsupport import _ENV_KEYS, register_server  # noqa: F401 (re-exported for test modules)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class FakeLifecycleClient:
    """In-memory fake of the EcsLifecycleClient interface used by service tests."""

    def __init__(self) -> None:
        self.servers: list[dict[str, Any]] = []
        self.jobs: dict[str, dict[str, Any]] = {}
        self.images: list[dict[str, Any]] = []
        self.flavors: list[dict[str, Any]] = []
        self.keypairs: list[dict[str, Any]] = []
        self.subnets: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_all_servers(self) -> list[dict[str, Any]]:
        self.calls.append(("list_all_servers", {}))
        return list(self.servers)

    async def show_server(self, server_id: str) -> dict[str, Any]:
        self.calls.append(("show_server", {"server_id": server_id}))
        for server in self.servers:
            if server.get("id") == server_id:
                return {"server": dict(server)}
        raise AssertionError(f"show_server called for unknown id {server_id}")

    async def create_pre_paid_server(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("create_pre_paid_server", kwargs))
        return {"job_id": "job-create-1", "order_id": "order-1", "server_ids": ["srv-new-1"]}

    async def create_post_paid_server(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("create_post_paid_server", kwargs))
        return {"job_id": "job-create-2", "server_ids": ["srv-new-2"]}

    async def update_server(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("update_server", kwargs))
        return {}

    async def delete_servers(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("delete_servers", kwargs))
        return {"job_id": "job-delete-1"}

    async def show_job(self, job_id: str) -> dict[str, Any]:
        self.calls.append(("show_job", {"job_id": job_id}))
        return dict(self.jobs.get(job_id, {}))

    async def list_images(self) -> list[dict[str, Any]]:
        self.calls.append(("list_images", {}))
        return list(self.images)

    async def list_flavors(self, flavor_id: str | None = None) -> list[dict[str, Any]]:
        self.calls.append(("list_flavors", {"flavor_id": flavor_id}))
        if flavor_id is not None:
            return [f for f in self.flavors if f.get("id") == flavor_id]
        return list(self.flavors)

    async def list_keypairs(self) -> list[dict[str, Any]]:
        self.calls.append(("list_keypairs", {}))
        return list(self.keypairs)

    async def list_subnets(self) -> list[dict[str, Any]]:
        self.calls.append(("list_subnets", {}))
        return list(self.subnets)


@pytest.fixture
def fake_client() -> FakeLifecycleClient:
    return FakeLifecycleClient()
