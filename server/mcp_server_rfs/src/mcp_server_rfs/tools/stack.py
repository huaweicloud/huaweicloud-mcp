# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Scenario tools for RFS resource stacks (full lifecycle)."""

from __future__ import annotations

from typing import Any

from huaweicloud_mcp_core.security import ToolRisk, guard

from mcp_server_rfs.server import mcp
from mcp_server_rfs.service.stack_service import StackService


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def list_stacks(
    name: str | None = None,
    limit: int = 20,
    marker: str | None = None,
) -> dict[str, Any]:
    """List RFS resource stacks in the current region.

    Scenario: user wants an inventory of infrastructure stacks — what exists,
    its deployment status, and whether deletion protection is on.

    Args:
        name: optional case-insensitive substring filter on stack name.
        limit: max stacks to return, 1-100 (default 20).
        marker: pagination marker returned by a previous call.

    Returns:
        Paginated envelope with items (stack_id, stack_name, status,
        description, create_time, enable_deletion_protection).
    """
    return await StackService().list_stacks(name=name, limit=limit, marker=marker)


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def get_stack(stack_name: str) -> dict[str, Any]:
    """Get one RFS stack: metadata plus its outputs.

    Scenario: user deployed a stack and wants its current state and output
    values (e.g. the EIP or load balancer address the stack created).

    Args:
        stack_name: stack name (e.g. "web-app-prod").

    Returns:
        Stack metadata (stack_id, status, status_message, create_time,
        enable_deletion_protection) and an outputs map.
    """
    return await StackService().get_stack(stack_name=stack_name)


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def preview_stack_changes(
    stack_name: str,
    template: str | None = None,
    template_uri: str | None = None,
    variables: dict[str, str] | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Dry-run a template against an existing stack and preview the diff.

    Scenario: user changed an HCL template (or variables) and wants to know
    what would be added, replaced or removed before actually deploying.

    Args:
        stack_name: existing stack to plan against.
        template: full HCL template text (run this instead of template_uri).
        template_uri: OBS URL of an existing template (mutually exclusive
            with template).
        variables: template variables as a key/value map.
        timeout_seconds: max seconds to wait for plan generation (default 60).

    Returns:
        execution_plan_id, status, per-action summary counts and up to 50
        changed resources (action, resource_name, resource_type).
    """
    return await StackService().preview_stack_changes(
        stack_name=stack_name,
        template=template,
        template_uri=template_uri,
        variables=variables,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
@guard(risk=ToolRisk.WRITE)
async def deploy_stack(
    stack_name: str,
    template: str | None = None,
    template_uri: str | None = None,
    variables: dict[str, str] | None = None,
    enable_deletion_protection: bool = False,
    wait: bool = False,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Deploy an HCL template: create the stack, or update it if it exists.

    Scenario: user wants infrastructure as code in one step — pass a
    template (inline or OBS URL) plus variables; the tool creates or updates
    the named stack and reports status and outputs.

    Args:
        stack_name: target stack name (e.g. "web-app-prod").
        template: full HCL template text. Required unless template_uri is set.
        template_uri: OBS URL of an existing template (mutually exclusive
            with template).
        variables: template variables as a key/value map.
        enable_deletion_protection: enable RFS deletion protection on create
            (default false).
        wait: if true, poll until the deployment reaches a terminal state
            (up to timeout_seconds); default returns immediately.
        timeout_seconds: max seconds to wait when wait=true (default 300).

    Returns:
        action (created/updated), status, deployment_id and, once complete,
        the stack outputs. On failure, run diagnose_stack next.
    """
    return await StackService().deploy_stack(
        stack_name=stack_name,
        template=template,
        template_uri=template_uri,
        variables=variables,
        enable_deletion_protection=enable_deletion_protection,
        wait=wait,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def diagnose_stack(stack_name: str, event_limit: int = 20) -> dict[str, Any]:
    """Diagnose a stack: aggregate status, failed events and failed resources.

    Scenario: a deployment failed or a stack is stuck and the user wants the
    root cause — the tool joins stack status, recent failed events and failed
    resources into conclusions with next-step hints.

    Args:
        stack_name: stack to diagnose.
        event_limit: how many recent events to inspect, 1-100 (default 20).

    Returns:
        stack summary, recent_failed_events, failed_resources, analysis
        (root-cause conclusions) and hints (recommended next actions).
    """
    return await StackService().diagnose_stack(stack_name=stack_name, event_limit=event_limit)


@mcp.tool()
@guard(risk=ToolRisk.DANGEROUS)
async def delete_stack(
    stack_name: str,
    retain_resources: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Delete an RFS stack and (by default) all resources it created.

    Scenario: user wants to tear down a stack. With confirm=false the tool
    returns a preview (resources that would be deleted, type distribution);
    call again with confirm=true to actually delete.

    Args:
        stack_name: stack to delete.
        retain_resources: if true, keep the cloud resources and only remove
            the stack record (default false — resources are deleted).
        confirm: must be explicitly true to execute; false returns a preview.

    Returns:
        With confirm=false: confirmation_required plus a preview of affected
        resources. With confirm=true: deletion result.
    """
    return await StackService().delete_stack(
        stack_name=stack_name,
        retain_resources=retain_resources,
        confirm=confirm,
    )
