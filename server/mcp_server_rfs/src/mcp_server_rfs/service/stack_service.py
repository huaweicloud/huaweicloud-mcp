# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Service layer: scenario orchestration for RFS stacks."""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from typing import Any

from huaweicloud_mcp_core.errors import McpToolError
from huaweicloud_mcp_core.guardrails import assert_not_protected
from huaweicloud_mcp_core.output import clamp_limit, page_result, single_result

from mcp_server_rfs.client.rfs_client import RfsClient

_IN_PROGRESS = {
    "CREATION_IN_PROGRESS",
    "DEPLOYMENT_IN_PROGRESS",
    "ROLLBACK_IN_PROGRESS",
    "DELETION_IN_PROGRESS",
    "OPERATION_IN_PROGRESS",
}
_FAILED = {
    "CREATION_FAILED",
    "DEPLOYMENT_FAILED",
    "ROLLBACK_FAILED",
    "DELETION_FAILED",
    "OPERATION_FAILED",
}
_COMPLETE = {
    "CREATION_COMPLETE",
    "DEPLOYMENT_COMPLETE",
    "ROLLBACK_COMPLETE",
    "DELETION_COMPLETE",
    "OPERATION_COMPLETE",
}

_STACK_FIELDS = (
    "stack_id",
    "stack_name",
    "status",
    "status_message",
    "description",
    "create_time",
    "update_time",
    "enable_deletion_protection",
)

_EVENT_FIELDS = (
    "event_time",
    "resource_name",
    "resource_type",
    "status",
    "status_reason",
    "physical_resource_id",
)

_RESOURCE_FIELDS = (
    "resource_name",
    "resource_type",
    "status",
    "status_message",
    "physical_resource_id",
)

_POLL_INTERVAL_SECONDS = 5


def _pick(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in fields if source.get(key) is not None}


def _validate_template_args(template: str | None, template_uri: str | None) -> None:
    if not template and not template_uri:
        raise McpToolError(
            code="MCP_INVALID_ARGS",
            message="Either template (inline HCL string) or template_uri (OBS URL) is required.",
            hint=(
                "Pass the full HCL template text in `template`, or reference an existing "
                "template object with `template_uri`."
            ),
        )
    if template and template_uri:
        raise McpToolError(
            code="MCP_INVALID_ARGS",
            message="Provide only one of template or template_uri, not both.",
            hint="Inline templates take precedence in most workflows; drop one argument.",
        )


class StackService:
    """Scenario orchestration for the RFS stack lifecycle."""

    def __init__(self, client: RfsClient | None = None) -> None:
        self._client = client or RfsClient()

    async def list_stacks(
        self,
        *,
        name: str | None = None,
        limit: int = 20,
        marker: str | None = None,
    ) -> dict[str, Any]:
        limit = clamp_limit(limit)
        response = await self._client.list_stacks(limit=limit, marker=marker)
        stacks = [_pick(stack, _STACK_FIELDS) for stack in response.get("stacks") or []]
        if name:
            stacks = [
                stack
                for stack in stacks
                if name.lower() in str(stack.get("stack_name", "")).lower()
            ]
        next_marker = (response.get("page_info") or {}).get("next_marker")
        return page_result(stacks, total=None, marker=next_marker)

    async def get_stack(self, *, stack_name: str) -> dict[str, Any]:
        meta = await self._require_stack(stack_name)
        outputs_raw = await self._client.list_stack_outputs(stack_name=stack_name)
        outputs = outputs_raw.get("outputs") or outputs_raw.get("stack_outputs") or []
        output_map = {
            str(item.get("output_key")): item.get("output_value")
            for item in outputs
            if isinstance(item, dict)
        }
        payload = _pick(meta, _STACK_FIELDS)
        payload["outputs"] = output_map
        return single_result(payload)

    async def deploy_stack(
        self,
        *,
        stack_name: str,
        template: str | None = None,
        template_uri: str | None = None,
        variables: dict[str, str] | None = None,
        enable_deletion_protection: bool = False,
        wait: bool = False,
        timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        _validate_template_args(template, template_uri)
        meta = await self._client.get_stack_metadata(stack_name)
        if meta is None:
            await self._client.create_stack(
                stack_name=stack_name,
                template_body=template,
                template_uri=template_uri,
                variables=variables,
                enable_deletion_protection=enable_deletion_protection,
            )
            action = "created"
            deployment: dict[str, Any] = {}
        else:
            status = str(meta.get("status") or "")
            if status in _IN_PROGRESS:
                raise McpToolError(
                    code="MCP_INVALID_STATE",
                    message=(
                        f"Stack '{stack_name}' is in progress ({status}); "
                        "concurrent deploys are not allowed."
                    ),
                    hint=(
                        "Check progress with get_stack, then deploy again once it "
                        "reaches a terminal state."
                    ),
                )
            deployment = await self._client.deploy_stack(
                stack_name=stack_name,
                template_body=template,
                template_uri=template_uri,
                variables=variables,
            )
            action = "updated"

        result: dict[str, Any] = {
            "stack_name": stack_name,
            "action": action,
            "status": None,
            "deployment_id": deployment.get("deployment_id"),
        }
        if wait:
            meta = await self._wait_terminal(stack_name, timeout_seconds)
            result["waited"] = True
            result["status"] = meta.get("status")
            result["status_message"] = meta.get("status_message")
            if str(meta.get("status")) in _COMPLETE:
                result["outputs"] = await self._fetch_outputs(stack_name)
        hints = ["Track progress with get_stack or diagnose_stack."]
        if str(result.get("status")) in _FAILED:
            hints.append("Deployment failed; run diagnose_stack to locate the failing resource.")
        result["hints"] = hints
        return result

    async def preview_stack_changes(
        self,
        *,
        stack_name: str,
        template: str | None = None,
        template_uri: str | None = None,
        variables: dict[str, str] | None = None,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        _validate_template_args(template, template_uri)
        plan = await self._client.create_execution_plan(
            stack_name=stack_name,
            template_body=template,
            template_uri=template_uri,
            variables=variables,
        )
        plan_id = str(plan.get("execution_plan_id") or "")
        metadata = await self._wait_execution_plan(stack_name, plan_id, timeout_seconds)
        detail = await self._client.get_execution_plan(
            stack_name=stack_name, execution_plan_id=plan_id
        )
        items = detail.get("execution_plan_items") or []
        summarized = [
            {
                "action": item.get("action"),
                "resource_name": item.get("resource_name"),
                "resource_type": item.get("resource_type"),
                "resource_id": item.get("resource_id"),
            }
            for item in items
            if isinstance(item, dict)
        ][:50]
        action_counts = dict(Counter(str(item.get("action")) for item in summarized))
        return {
            "stack_name": stack_name,
            "execution_plan_id": plan_id,
            "status": metadata.get("status"),
            "summary": action_counts,
            "items": summarized,
            "hints": [
                "Apply these changes with deploy_stack using the same template and variables."
            ],
        }

    async def diagnose_stack(self, *, stack_name: str, event_limit: int = 20) -> dict[str, Any]:
        meta = await self._require_stack(stack_name)
        events_raw = await self._client.list_stack_events(
            stack_name=stack_name, limit=clamp_limit(event_limit)
        )
        resources_raw = await self._client.list_stack_resources(stack_name=stack_name)
        events = [_pick(event, _EVENT_FIELDS) for event in events_raw.get("stack_events") or []]
        events.sort(key=lambda item: str(item.get("event_time") or ""), reverse=True)
        resources = [
            _pick(resource, _RESOURCE_FIELDS)
            for resource in resources_raw.get("stack_resources") or []
        ]
        failed_events = [event for event in events if "FAIL" in str(event.get("status") or "")]
        failed_resources = [
            resource for resource in resources if "FAIL" in str(resource.get("status") or "")
        ]
        status = str(meta.get("status") or "")
        analysis: list[str] = []
        if status in _IN_PROGRESS:
            analysis.append(f"An operation is in progress ({status}); failures may be transient.")
        if failed_events:
            latest = failed_events[0]
            analysis.append(
                f"Most recent failure: resource '{latest.get('resource_name')}' "
                f"({latest.get('resource_type')}) — "
                f"{latest.get('status_reason') or 'no reason recorded'}."
            )
        if status == "ROLLBACK_FAILED":
            analysis.append(
                "Rollback failed; the stack is in an inconsistent state and needs manual attention."
            )
        if not analysis:
            analysis.append("No failure signals found in recent events or resources.")
        hints: list[str] = []
        if status == "ROLLBACK_FAILED":
            hints.append(
                "Continue the rollback from the console (Continue Rollback) or contact support."
            )
        elif status in _FAILED:
            hints.append(
                "Fix the template or variables, then run deploy_stack again; "
                "RFS rolls back failed deployments automatically."
            )
        elif status in _IN_PROGRESS:
            hints.append("Run diagnose_stack again after the current operation completes.")
        else:
            hints.append("Stack looks healthy; inspect outputs with get_stack.")
        return {
            "stack": _pick(meta, _STACK_FIELDS),
            "recent_failed_events": failed_events[:10],
            "failed_resources": failed_resources,
            "analysis": analysis,
            "hints": hints,
        }

    async def delete_stack(
        self,
        *,
        stack_name: str,
        retain_resources: bool = False,
        confirm: bool = False,
    ) -> dict[str, Any]:
        meta = await self._require_stack(stack_name)
        if meta.get("enable_deletion_protection"):
            raise McpToolError(
                code="MCP_DELETION_PROTECTED",
                message=f"Stack '{stack_name}' has deletion protection enabled.",
                hint=(
                    "Disable deletion protection (deploy_stack update or console) before deleting."
                ),
            )
        if not confirm:
            resources_raw = await self._client.list_stack_resources(stack_name=stack_name)
            resources = resources_raw.get("stack_resources") or []
            type_counts = dict(
                Counter(str(item.get("resource_type") or "unknown") for item in resources)
            )
            preview = {
                "stack_name": stack_name,
                "stack_id": meta.get("stack_id"),
                "status": meta.get("status"),
                "tags": {},
                "resource_count": len(resources),
                "resource_types": type_counts,
                "retain_resources": retain_resources,
            }
            return {
                "confirmation_required": True,
                "preview": preview,
                "message": (
                    "This operation is irreversible"
                    + (
                        " (resources will be retained, only the stack record is removed)"
                        if retain_resources
                        else " and will delete all resources in the stack"
                    )
                    + ". Call again with confirm=true to proceed."
                ),
            }
        assert_not_protected(
            {"id": meta.get("stack_id") or "", "name": stack_name, "tags": {}},
            tool_name="delete_stack",
        )
        await self._client.delete_stack(
            stack_name=stack_name, retain_all_resources=retain_resources
        )
        return {
            "stack_name": stack_name,
            "deleted": True,
            "retain_resources": retain_resources,
            "hints": ["Deletion runs asynchronously; verify with list_stacks."],
        }

    async def _require_stack(self, stack_name: str) -> dict[str, Any]:
        meta = await self._client.get_stack_metadata(stack_name)
        if meta is None:
            raise McpToolError(
                code="MCP_NOT_FOUND",
                message=f"Stack '{stack_name}' not found.",
                hint="Run list_stacks to see existing stacks in this region.",
            )
        return meta

    async def _wait_terminal(
        self,
        stack_name: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            meta = await self._client.get_stack_metadata(stack_name)
            if meta is None:
                raise McpToolError(
                    code="MCP_NOT_FOUND",
                    message=f"Stack '{stack_name}' disappeared while waiting.",
                    hint="Check list_stacks; the stack may have been deleted concurrently.",
                )
            status = str(meta.get("status") or "")
            if status in _FAILED or status in _COMPLETE:
                return meta
            if time.monotonic() >= deadline:
                return meta
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    async def _wait_execution_plan(
        self,
        stack_name: str,
        plan_id: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            plan = await self._client.get_execution_plan_metadata(
                stack_name=stack_name, execution_plan_id=plan_id
            )
            status = str(plan.get("status") or "")
            if status == "AVAILABLE":
                return plan
            if "FAILED" in status or "ERROR" in status:
                raise McpToolError(
                    code="MCP_EXECUTION_PLAN_FAILED",
                    message=(
                        f"Execution plan creation failed: {plan.get('status_message') or status}"
                    ),
                    hint="Fix the template or variables and retry preview_stack_changes.",
                )
            if time.monotonic() >= deadline:
                raise McpToolError(
                    code="MCP_TIMEOUT",
                    message=(
                        f"Execution plan '{plan_id}' did not become AVAILABLE in "
                        f"{timeout_seconds}s."
                    ),
                    hint="Retry preview_stack_changes or increase timeout_seconds.",
                )
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    async def _fetch_outputs(self, stack_name: str) -> dict[str, Any]:
        outputs_raw = await self._client.list_stack_outputs(stack_name=stack_name)
        outputs = outputs_raw.get("outputs") or outputs_raw.get("stack_outputs") or []
        return {
            str(item.get("output_key")): item.get("output_value")
            for item in outputs
            if isinstance(item, dict)
        }
