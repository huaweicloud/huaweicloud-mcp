# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the RFS service layer (orchestration scenarios)."""

from __future__ import annotations

from typing import Any

import pytest

from huaweicloud_mcp_core.errors import McpToolError
from mcp_server_rfs.service.stack_service import StackService

from conftest import FakeRfsClient, register_stack


@pytest.fixture
def service(fake_client: FakeRfsClient) -> StackService:
    return StackService(client=fake_client)


async def test_list_stacks_paginates_and_filters(service: StackService, fake_client: FakeRfsClient) -> None:
    register_stack(fake_client, "web-prod")
    register_stack(fake_client, "web-dev")
    register_stack(fake_client, "db-prod")
    fake_client.next_marker = "marker-2"
    result = await service.list_stacks(name="web", limit=10)
    assert [item["stack_name"] for item in result["items"]] == ["web-prod", "web-dev"]
    assert result["count"] == 2
    assert result["marker"] == "marker-2"


async def test_list_stacks_limit_is_clamped(service: StackService, fake_client: FakeRfsClient) -> None:
    register_stack(fake_client, "s1")
    result = await service.list_stacks(limit=5000)
    assert fake_client.calls[-1][1]["limit"] == 100
    assert result["count"] == 1


async def test_get_stack_returns_outputs(service: StackService, fake_client: FakeRfsClient) -> None:
    register_stack(fake_client, "web")
    fake_client.outputs["web"] = [
        {"output_key": "eip", "output_value": "1.2.3.4"},
        {"output_key": "vpc_id", "output_value": "vpc-9"},
    ]
    result = await service.get_stack(stack_name="web")
    assert result["stack_id"] == "sid-web"
    assert result["outputs"] == {"eip": "1.2.3.4", "vpc_id": "vpc-9"}


async def test_get_stack_missing_raises(service: StackService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.get_stack(stack_name="nope")
    assert excinfo.value.code == "MCP_NOT_FOUND"
    assert "list_stacks" in (excinfo.value.hint or "")


async def test_deploy_creates_when_absent(service: StackService, fake_client: FakeRfsClient) -> None:
    result = await service.deploy_stack(
        stack_name="fresh",
        template="resource \"huaweicloud_vpc\" \"main\" {}",
        variables={"env": "dev"},
    )
    assert result["action"] == "created"
    assert fake_client.calls[-1][0] == "create_stack"
    call = fake_client.calls[-1][1]
    assert call["template_body"] == "resource \"huaweicloud_vpc\" \"main\" {}"
    assert call["variables"] == {"env": "dev"}
    assert call["enable_deletion_protection"] is False
    assert "Track progress" in result["hints"][0]


async def test_deploy_updates_when_exists(service: StackService, fake_client: FakeRfsClient) -> None:
    register_stack(fake_client, "web", status="DEPLOYMENT_COMPLETE")
    result = await service.deploy_stack(
        stack_name="web",
        template_uri="https://obs.example.com/tpl",
    )
    assert result["action"] == "updated"
    assert result["deployment_id"] == "dep-42"
    assert fake_client.calls[-1][0] == "deploy_stack"
    assert fake_client.calls[-1][1]["template_uri"] == "https://obs.example.com/tpl"


async def test_deploy_rejects_while_in_progress(service: StackService, fake_client: FakeRfsClient) -> None:
    register_stack(fake_client, "web", status="DEPLOYMENT_IN_PROGRESS")
    with pytest.raises(McpToolError) as excinfo:
        await service.deploy_stack(stack_name="web", template="t")
    assert excinfo.value.code == "MCP_INVALID_STATE"


async def test_deploy_requires_template_argument(service: StackService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.deploy_stack(stack_name="x")
    assert excinfo.value.code == "MCP_INVALID_ARGS"
    assert "template" in excinfo.value.message


async def test_deploy_rejects_both_template_channels(service: StackService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.deploy_stack(stack_name="x", template="t", template_uri="u")
    assert excinfo.value.code == "MCP_INVALID_ARGS"


async def test_deploy_wait_polls_until_complete(
    service: StackService,
    fake_client: FakeRfsClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mcp_server_rfs.service.stack_service._POLL_INTERVAL_SECONDS", 0)
    register_stack(fake_client, "web", status="DEPLOYMENT_IN_PROGRESS")
    fake_client.status_queue = ["DEPLOYMENT_COMPLETE"]
    fake_client.outputs["web"] = [{"output_key": "eip", "output_value": "1.1.1.1"}]
    result = await service.deploy_stack(
        stack_name="web", template="t", wait=True, timeout_seconds=5
    )
    assert result["waited"] is True
    assert result["status"] == "DEPLOYMENT_COMPLETE"
    assert result["outputs"] == {"eip": "1.1.1.1"}


async def test_deploy_wait_timeout_returns_current_status(
    service: StackService,
    fake_client: FakeRfsClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mcp_server_rfs.service.stack_service._POLL_INTERVAL_SECONDS", 0)
    register_stack(fake_client, "web", status="DEPLOYMENT_COMPLETE")
    fake_client.status_queue = ["DEPLOYMENT_COMPLETE", "DEPLOYMENT_IN_PROGRESS"]
    result = await service.deploy_stack(
        stack_name="web", template="t", wait=True, timeout_seconds=0
    )
    assert result["status"] == "DEPLOYMENT_IN_PROGRESS"


async def test_preview_returns_diff_summary(
    service: StackService,
    fake_client: FakeRfsClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mcp_server_rfs.service.stack_service._POLL_INTERVAL_SECONDS", 0)
    register_stack(fake_client, "web")
    fake_client.plan_status_queue = ["AVAILABLE"]
    fake_client.plans["plan-1"] = {
        "execution_plan_id": "plan-1",
        "status": "CREATION_IN_PROGRESS",
        "execution_plan_items": [
            {"action": "ADD", "resource_name": "vpc", "resource_type": "huaweicloud_vpc"},
            {"action": "ADD", "resource_name": "subnet", "resource_type": "huaweicloud_vpc_subnet"},
            {"action": "REMOVE", "resource_name": "old_eip", "resource_type": "huaweicloud_vpc_eip"},
        ],
    }
    result = await service.preview_stack_changes(stack_name="web", template="t")
    assert result["execution_plan_id"] == "plan-1"
    assert result["status"] == "AVAILABLE"
    assert result["summary"] == {"ADD": 2, "REMOVE": 1}
    assert result["items"][0]["resource_name"] == "vpc"


async def test_preview_failed_plan_raises(
    service: StackService,
    fake_client: FakeRfsClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mcp_server_rfs.service.stack_service._POLL_INTERVAL_SECONDS", 0)
    register_stack(fake_client, "web")
    fake_client.plan_status_queue = ["CREATION_FAILED"]
    with pytest.raises(McpToolError) as excinfo:
        await service.preview_stack_changes(stack_name="web", template="t")
    assert excinfo.value.code == "MCP_EXECUTION_PLAN_FAILED"


async def test_preview_timeout_raises(
    service: StackService,
    fake_client: FakeRfsClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mcp_server_rfs.service.stack_service._POLL_INTERVAL_SECONDS", 0)
    register_stack(fake_client, "web")
    with pytest.raises(McpToolError) as excinfo:
        await service.preview_stack_changes(stack_name="web", template="t", timeout_seconds=0)
    assert excinfo.value.code == "MCP_TIMEOUT"


async def test_diagnose_aggregates_failures(service: StackService, fake_client: FakeRfsClient) -> None:
    register_stack(fake_client, "web", status="DEPLOYMENT_FAILED", status_message="deploy failed")
    fake_client.events["web"] = [
        {"event_time": "t2", "resource_name": "eip", "resource_type": "huaweicloud_vpc_eip",
         "status": "CREATE_FAILED", "status_reason": "quota exceeded"},
        {"event_time": "t1", "resource_name": "vpc", "resource_type": "huaweicloud_vpc",
         "status": "CREATE_COMPLETE", "status_reason": None},
    ]
    fake_client.resources["web"] = [
        {"resource_name": "eip", "resource_type": "huaweicloud_vpc_eip",
         "status": "CREATE_FAILED", "status_message": "quota exceeded"},
    ]
    result = await service.diagnose_stack(stack_name="web")
    assert result["stack"]["status"] == "DEPLOYMENT_FAILED"
    assert result["recent_failed_events"][0]["resource_name"] == "eip"
    assert result["failed_resources"][0]["resource_name"] == "eip"
    assert any("quota exceeded" in line for line in result["analysis"])
    assert any("deploy_stack" in hint for hint in result["hints"])


async def test_diagnose_rollback_failed_recommends_manual_action(
    service: StackService,
    fake_client: FakeRfsClient,
) -> None:
    register_stack(fake_client, "web", status="ROLLBACK_FAILED")
    fake_client.events["web"] = []
    fake_client.resources["web"] = []
    result = await service.diagnose_stack(stack_name="web")
    assert any("inconsistent state" in line for line in result["analysis"])
    assert any("rollback" in hint.lower() for hint in result["hints"])


async def test_diagnose_healthy_stack(service: StackService, fake_client: FakeRfsClient) -> None:
    register_stack(fake_client, "web", status="DEPLOYMENT_COMPLETE")
    fake_client.events["web"] = []
    fake_client.resources["web"] = [
        {"resource_name": "vpc", "resource_type": "huaweicloud_vpc", "status": "CREATE_COMPLETE"},
    ]
    result = await service.diagnose_stack(stack_name="web")
    assert result["failed_resources"] == []
    assert result["recent_failed_events"] == []
    assert result["analysis"] == ["No failure signals found in recent events or resources."]


async def test_delete_without_confirm_returns_preview(
    service: StackService,
    fake_client: FakeRfsClient,
) -> None:
    register_stack(fake_client, "web")
    fake_client.resources["web"] = [
        {"resource_name": "vpc", "resource_type": "huaweicloud_vpc"},
        {"resource_name": "eip", "resource_type": "huaweicloud_vpc_eip"},
        {"resource_name": "eip2", "resource_type": "huaweicloud_vpc_eip"},
    ]
    result = await service.delete_stack(stack_name="web")
    assert result["confirmation_required"] is True
    assert result["preview"]["stack_name"] == "web"
    assert result["preview"]["resource_count"] == 3
    assert result["preview"]["resource_types"] == {
        "huaweicloud_vpc": 1,
        "huaweicloud_vpc_eip": 2,
    }
    assert "tags" in result["preview"]
    assert all(call[0] != "delete_stack" for call in fake_client.calls)


async def test_delete_respects_deletion_protection(
    service: StackService,
    fake_client: FakeRfsClient,
) -> None:
    register_stack(fake_client, "web", enable_deletion_protection=True)
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_stack(stack_name="web", confirm=True)
    assert excinfo.value.code == "MCP_DELETION_PROTECTED"


async def test_delete_with_confirm_deletes(
    service: StackService,
    fake_client: FakeRfsClient,
) -> None:
    register_stack(fake_client, "web")
    result = await service.delete_stack(stack_name="web", confirm=True)
    assert result["deleted"] is True
    assert fake_client.calls[-1] == (
        "delete_stack",
        {"stack_name": "web", "retain_all_resources": False},
    )
    assert "web" not in fake_client.stacks


async def test_delete_with_confirm_retains_resources(
    service: StackService,
    fake_client: FakeRfsClient,
) -> None:
    register_stack(fake_client, "web")
    await service.delete_stack(stack_name="web", retain_resources=True, confirm=True)
    assert fake_client.calls[-1][1]["retain_all_resources"] is True


async def test_delete_blocked_by_protection_rule(
    service: StackService,
    fake_client: FakeRfsClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_NAMES", "prod-web")
    register_stack(fake_client, "prod-web")
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_stack(stack_name="prod-web", confirm=True)
    assert excinfo.value.code == "MCP_GUARDRAIL_BLOCKED"
    assert all(call[0] != "delete_stack" for call in fake_client.calls)


async def test_delete_missing_stack_raises(service: StackService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_stack(stack_name="ghost", confirm=True)
    assert excinfo.value.code == "MCP_NOT_FOUND"
