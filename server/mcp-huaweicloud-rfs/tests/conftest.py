# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Shared fixtures for the RFS server tests."""

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


class FakeRfsClient:
    """In-memory fake of the RfsClient interface used by service tests."""

    def __init__(self) -> None:
        self.stacks: dict[str, dict[str, Any]] = {}
        self.resources: dict[str, list[dict[str, Any]]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.outputs: dict[str, list[dict[str, Any]]] = {}
        self.plans: dict[str, dict[str, Any]] = {}
        self.status_queue: list[str] = []
        self.plan_status_queue: list[str] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.next_marker: str | None = None
        self.deploy_response: dict[str, Any] = {"deployment_id": "dep-42"}
        self.create_response: dict[str, Any] = {"stack_id": "sid-new"}

    async def list_stacks(self, *, limit: int, marker: str | None) -> dict[str, Any]:
        self.calls.append(("list_stacks", {"limit": limit, "marker": marker}))
        items = list(self.stacks.values())
        return {
            "stacks": items[:limit],
            "page_info": {"next_marker": self.next_marker},
        }

    async def get_stack_metadata(self, stack_name: str) -> dict[str, Any] | None:
        self.calls.append(("get_stack_metadata", {"stack_name": stack_name}))
        if self.status_queue:
            status = self.status_queue.pop(0)
            if stack_name in self.stacks:
                self.stacks[stack_name]["status"] = status
        return self.stacks.get(stack_name)

    async def create_stack(
        self,
        *,
        stack_name: str,
        template_body: str | None,
        template_uri: str | None,
        variables: dict[str, str] | None,
        enable_deletion_protection: bool,
        description: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "create_stack",
                {
                    "stack_name": stack_name,
                    "template_body": template_body,
                    "template_uri": template_uri,
                    "variables": variables,
                    "enable_deletion_protection": enable_deletion_protection,
                },
            )
        )
        self.stacks[stack_name] = {
            "stack_id": "sid-new",
            "stack_name": stack_name,
            "status": "CREATION_IN_PROGRESS",
            "enable_deletion_protection": enable_deletion_protection,
        }
        return dict(self.create_response)

    async def deploy_stack(
        self,
        *,
        stack_name: str,
        template_body: str | None,
        template_uri: str | None,
        variables: dict[str, str] | None,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "deploy_stack",
                {
                    "stack_name": stack_name,
                    "template_body": template_body,
                    "template_uri": template_uri,
                    "variables": variables,
                },
            )
        )
        return dict(self.deploy_response)

    async def delete_stack(self, *, stack_name: str, retain_all_resources: bool) -> dict[str, Any]:
        self.calls.append(
            ("delete_stack", {"stack_name": stack_name, "retain_all_resources": retain_all_resources})
        )
        self.stacks.pop(stack_name, None)
        return {}

    async def list_stack_events(
        self,
        *,
        stack_name: str,
        limit: int,
        marker: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("list_stack_events", {"stack_name": stack_name, "limit": limit}))
        return {"stack_events": list(self.events.get(stack_name, []))[:limit]}

    async def list_stack_resources(self, *, stack_name: str) -> dict[str, Any]:
        self.calls.append(("list_stack_resources", {"stack_name": stack_name}))
        return {"stack_resources": list(self.resources.get(stack_name, []))}

    async def list_stack_outputs(self, *, stack_name: str) -> dict[str, Any]:
        self.calls.append(("list_stack_outputs", {"stack_name": stack_name}))
        return {"outputs": list(self.outputs.get(stack_name, []))}

    async def create_execution_plan(
        self,
        *,
        stack_name: str,
        template_body: str | None,
        template_uri: str | None,
        variables: dict[str, str] | None,
    ) -> dict[str, Any]:
        self.calls.append(("create_execution_plan", {"stack_name": stack_name}))
        self.plans.setdefault(
            "plan-1",
            {
                "execution_plan_id": "plan-1",
                "status": "CREATION_IN_PROGRESS",
                "execution_plan_items": [],
            },
        )
        return {"execution_plan_id": "plan-1"}

    async def get_execution_plan_metadata(
        self,
        *,
        stack_name: str,
        execution_plan_id: str,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "get_execution_plan_metadata",
                {"stack_name": stack_name, "execution_plan_id": execution_plan_id},
            )
        )
        plan = self.plans.get(execution_plan_id, {})
        if self.plan_status_queue:
            plan["status"] = self.plan_status_queue.pop(0)
        return dict(plan)

    async def get_execution_plan(self, *, stack_name: str, execution_plan_id: str) -> dict[str, Any]:
        self.calls.append(
            ("get_execution_plan", {"stack_name": stack_name, "execution_plan_id": execution_plan_id})
        )
        return {"execution_plan_items": list(self.plans.get(execution_plan_id, {}).get("execution_plan_items", []))}


@pytest.fixture
def fake_client() -> FakeRfsClient:
    return FakeRfsClient()


def register_stack(
    client: FakeRfsClient,
    name: str,
    status: str = "DEPLOYMENT_COMPLETE",
    **extra: Any,
) -> dict[str, Any]:
    stack: dict[str, Any] = {
        "stack_id": f"sid-{name}",
        "stack_name": name,
        "status": status,
        "status_message": None,
        "description": f"stack {name}",
        "create_time": "2026-01-01T00:00:00Z",
        "enable_deletion_protection": False,
    }
    stack.update(extra)
    client.stacks[name] = stack
    return stack
