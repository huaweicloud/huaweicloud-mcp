# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Service layer: scenario orchestration for PLACEHOLDER resources."""

from __future__ import annotations

from typing import Any

from huaweicloud_mcp_core.errors import McpToolError
from huaweicloud_mcp_core.guardrails import assert_not_protected
from huaweicloud_mcp_core.output import clamp_limit, page_result, single_result

from mcp_server_PLACEHOLDER.client.placeholder_client import PlaceholderClient

_RESOURCE_FIELDS = (
    "id",
    "name",
    "status",
)


def _pick(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in fields if source.get(key) is not None}


class ResourceService:
    """Scenario orchestration for the PLACEHOLDER resource lifecycle."""

    def __init__(self, client: PlaceholderClient | None = None) -> None:
        self._client = client or PlaceholderClient()

    async def list_resources(
        self,
        *,
        name: str | None = None,
        limit: int = 20,
        marker: str | None = None,
    ) -> dict[str, Any]:
        limit = clamp_limit(limit)
        response = await self._client.list_resources(limit=limit, marker=marker)
        items = [_pick(item, _RESOURCE_FIELDS) for item in response.get("resources") or []]
        if name:
            items = [item for item in items if name.lower() in str(item.get("name", "")).lower()]
        return page_result(items, total=None, marker=None)

    async def delete_resource(self, *, resource_id: str, confirm: bool = False) -> dict[str, Any]:
        meta = await self._client.get_resource(resource_id)
        if meta is None:
            raise McpToolError(
                code="MCP_NOT_FOUND",
                message=f"Resource '{resource_id}' not found.",
                hint="Run list_resources to see existing resources in this region.",
            )
        if not confirm:
            return {
                "confirmation_required": True,
                "preview": {
                    "id": meta.get("id"),
                    "name": meta.get("name"),
                    "status": meta.get("status"),
                    "tags": meta.get("tags") or {},
                },
                "message": "This operation is irreversible. Call again with confirm=true to proceed.",
            }
        assert_not_protected(
            {"id": meta.get("id") or "", "name": meta.get("name") or "", "tags": meta.get("tags") or {}},
            tool_name="delete_resource",
        )
        await self._client.delete_resource(resource_id=resource_id)
        return {
            "resource_id": resource_id,
            "deleted": True,
            "hints": ["Deletion may be asynchronous; verify with list_resources."],
        }
