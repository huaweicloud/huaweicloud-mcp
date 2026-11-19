# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Shared fixtures for the ecs server tests."""

from __future__ import annotations

from typing import Any

import pytest
from huaweicloud_mcp_ecs_common.testsupport import _ENV_KEYS, register_server  # noqa: F401 (re-exported for test modules)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class FakeEcsClient:
    """In-memory fake of the EcsClient interface used by service tests."""

    def __init__(self) -> None:
        self.servers: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_all_servers(self) -> list[dict[str, Any]]:
        self.calls.append(("list_all_servers", {}))
        return list(self.servers)


@pytest.fixture
def fake_client() -> FakeEcsClient:
    return FakeEcsClient()
