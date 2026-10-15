"""Service layer: scenario orchestration for RC (Resource Center)."""

from __future__ import annotations

from typing import Any

from huaweicloud_mcp_core.errors import McpToolError
from huaweicloud_mcp_core.guardrails import assert_not_protected
from huaweicloud_mcp_core.output import clamp_limit, page_result, single_result

from mcp_server_rc.client.rc_client import RcClient

_PROVIDER_FIELDS = (
    "provider",
    "display_name",
    "category_display_name",
    "resource_types",
)

_RESOURCE_FIELDS = (
    "id",
    "name",
    "provider",
    "type",
    "region_id",
    "project_id",
    "project_name",
    "ep_id",
    "ep_name",
    "group_id",
    "purchase_model",
    "created",
    "updated",
    "provisioning_state",
    "tags",
    "state",
    "properties",
)

_TAG_FIELDS = (
    "key",
    "value",
)

_GROUP_FIELDS = (
    "group_id",
    "group_name",
    "description",
    "created",
    "updated",
)

_RELATION_FIELDS = (
    "resource_id",
    "resource_type",
    "related_resource_id",
    "related_resource_type",
)

_STORED_QUERY_FIELDS = (
    "id",
    "name",
    "description",
    "expression",
    "created",
    "updated",
)

_SUMMARY_FIELDS = (
    "provider",
    "types",
)

_SUMMARY_TYPE_FIELDS = (
    "type",
    "regions",
)

_SUMMARY_REGION_FIELDS = (
    "region_id",
    "count",
)


def _pick(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in fields if source.get(key) is not None}


def _pick_summary(source: dict[str, Any]) -> dict[str, Any]:
    item = _pick(source, _SUMMARY_FIELDS)
    types = item.get("types")
    if isinstance(types, list):
        cleaned: list[dict[str, Any]] = []
        for t in types:
            if not isinstance(t, dict):
                continue
            region = _pick(t, _SUMMARY_TYPE_FIELDS)
            regions = region.get("regions")
            if isinstance(regions, list):
                region["regions"] = [
                    _pick(r, _SUMMARY_REGION_FIELDS) for r in regions if isinstance(r, dict)
                ]
            cleaned.append(region)
        item["types"] = cleaned
    return item


def _next_marker(response: dict[str, Any]) -> str | None:
    return (response.get("page_info") or {}).get("next_marker")


class ResourceService:
    """Scenario orchestration for the RC resource center."""

    def __init__(self, client: RcClient | None = None) -> None:
        self._client = client or RcClient()

    # -- resource list -------------------------------------------------

    async def list_providers(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
        x_language: str | None = None,
    ) -> dict[str, Any]:
        if limit is not None:
            limit = clamp_limit(limit)
        response = await self._client.list_providers(
            offset=offset,
            limit=limit,
            x_language=x_language,
        )
        providers = response.get("resource_providers") or []
        items = [_pick(item, _PROVIDER_FIELDS) for item in providers if isinstance(item, dict)]
        total = len(items)
        return page_result(items, total=total, marker=None)

    async def list_all_resources(
        self,
        *,
        region_id: str | None = None,
        ep_id: str | None = None,
        resource_type: str | None = None,
        limit: int | None = None,
        marker: str | None = None,
        id_: str | None = None,
        group_id: str | None = None,
        name: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if limit is not None:
            limit = clamp_limit(limit)
        response = await self._client.list_all_resources(
            region_id=region_id,
            ep_id=ep_id,
            resource_type=resource_type,
            limit=limit,
            marker=marker,
            id_=id_,
            group_id=group_id,
            name=name,
            tags=tags,
        )
        resources = response.get("resources") or []
        items = [_pick(r, _RESOURCE_FIELDS) for r in resources if isinstance(r, dict)]
        return page_result(items, total=None, marker=_next_marker(response))

    async def show_resource_detail(self, *, resource_id: str) -> dict[str, Any]:
        resource = await self._client.show_resource_detail(resource_id=resource_id)
        if resource is None:
            raise _not_found("resource", resource_id)
        return single_result(_pick(resource, _RESOURCE_FIELDS))

    async def list_all_tags(
        self,
        *,
        key: str | None = None,
        limit: int | None = None,
        marker: str | None = None,
    ) -> dict[str, Any]:
        if limit is not None:
            limit = clamp_limit(limit)
        response = await self._client.list_all_tags(key=key, limit=limit, marker=marker)
        tags = response.get("tags") or []
        items = [_pick(t, _TAG_FIELDS) for t in tags if isinstance(t, dict)]
        return page_result(items, total=None, marker=_next_marker(response))

    async def count_all_resources(
        self,
        *,
        id_: str | None = None,
        name: str | None = None,
        group_id: str | None = None,
        resource_type: list[str] | None = None,
        region_id: list[str] | None = None,
        ep_id: list[str] | None = None,
        project_id: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        response = await self._client.count_all_resources(
            id_=id_,
            name=name,
            group_id=group_id,
            resource_type=resource_type,
            region_id=region_id,
            ep_id=ep_id,
            project_id=project_id,
            tags=tags,
        )
        return single_result({"total_count": response.get("total_count")})

    async def collect_resources_summary(
        self,
        *,
        name: str | None = None,
        resource_type: list[str] | None = None,
        region_id: list[str] | None = None,
        ep_id: list[str] | None = None,
        project_id: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        response = await self._client.collect_all_resources_summary(
            name=name,
            resource_type=resource_type,
            region_id=region_id,
            ep_id=ep_id,
            project_id=project_id,
            tags=tags,
        )
        body = response.get("body") or []
        items = [_pick_summary(item) for item in body if isinstance(item, dict)]
        return page_result(items, total=len(items), marker=None)

    # -- resource groups -----------------------------------------------------

    async def create_resource_group(
        self,
        *,
        group_name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        created = await self._client.create_resource_group(
            group_name=group_name,
            description=description,
        )
        return single_result(_pick(created, _GROUP_FIELDS))

    async def delete_resource_group(
        self,
        *,
        group_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        group = await self._client.show_resource_group(group_id=group_id)
        if group is None:
            raise _not_found("resource group", group_id)
        if not confirm:
            preview = _pick(group, _GROUP_FIELDS)
            return {
                "confirmation_required": True,
                "preview": preview,
                "message": (
                    "This operation is irreversible and will delete the resource group. "
                    "Call again with confirm=true to proceed."
                ),
            }
        assert_not_protected(
            {
                "id": str(group.get("group_id") or ""),
                "name": str(group.get("group_name") or ""),
                "tags": {},
            },
            tool_name="delete_resource_group",
        )
        await self._client.delete_resource_group(group_id=group_id)
        return {
            "group_id": group_id,
            "deleted": True,
            "hints": ["Verify with list_resource_groups."],
        }

    async def update_resource_group(
        self,
        *,
        group_id: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        group = await self._client.show_resource_group(group_id=group_id)
        if group is None:
            raise _not_found("resource group", group_id)
        updated = await self._client.update_resource_group(
            group_id=group_id,
            description=description,
        )
        return single_result(_pick(updated, _GROUP_FIELDS))

    async def show_resource_group(self, *, group_id: str) -> dict[str, Any]:
        group = await self._client.show_resource_group(group_id=group_id)
        if group is None:
            raise _not_found("resource group", group_id)
        return single_result(_pick(group, _GROUP_FIELDS))

    async def list_resource_groups(
        self,
        *,
        limit: int | None = None,
        marker: str | None = None,
    ) -> dict[str, Any]:
        if limit is not None:
            limit = clamp_limit(limit)
        response = await self._client.list_resource_groups(limit=limit, marker=marker)
        groups = response.get("resource_groups") or []
        items = [_pick(g, _GROUP_FIELDS) for g in groups if isinstance(g, dict)]
        return page_result(items, total=None, marker=_next_marker(response))

    async def add_resources_to_group(
        self,
        *,
        group_id: str,
        resource_ids: list[str],
    ) -> dict[str, Any]:
        group = await self._client.show_resource_group(group_id=group_id)
        if group is None:
            raise _not_found("resource group", group_id)
        response = await self._client.add_resources_to_group(
            group_id=group_id,
            resource_ids=resource_ids,
        )
        resources = response.get("resources") or []
        items = [_pick(r, _RESOURCE_FIELDS) for r in resources if isinstance(r, dict)]
        return page_result(items, total=len(items), marker=None)

    async def remove_resource_from_group(
        self,
        *,
        group_id: str,
        resource_id: str,
    ) -> dict[str, Any]:
        group = await self._client.show_resource_group(group_id=group_id)
        if group is None:
            raise _not_found("resource group", group_id)
        removed = await self._client.remove_resource_from_group(
            group_id=group_id,
            resource_id=resource_id,
        )
        return single_result(_pick(removed, _RESOURCE_FIELDS))

    # -- resource relationships ---------------------------------------------------

    async def show_resource_relations(
        self,
        *,
        resource_id: str,
        related_resource_id: str | None = None,
        related_resource_type: str | None = None,
        limit: int | None = None,
        marker: str | None = None,
    ) -> dict[str, Any]:
        if limit is not None:
            limit = clamp_limit(limit)
        response = await self._client.show_resource_relations(
            resource_id=resource_id,
            related_resource_id=related_resource_id,
            related_resource_type=related_resource_type,
            limit=limit,
            marker=marker,
        )
        relations = response.get("relations") or []
        items = [_pick(r, _RELATION_FIELDS) for r in relations if isinstance(r, dict)]
        return page_result(items, total=None, marker=_next_marker(response))

    # -- advanced queries --------------------------------------------------------

    async def run_query(
        self,
        *,
        expression: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        response = await self._client.run_query(expression=expression)
        results = response.get("results") or []
        items = [
            {key: value for key, value in item.items() if value is not None}
            for item in results
            if isinstance(item, dict)
        ]
        limit = clamp_limit(limit)
        total = len(items)
        items = items[:limit]
        return page_result(items, total=total, marker=None)

    async def create_stored_query(
        self,
        *,
        name: str,
        expression: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        created = await self._client.create_stored_query(
            name=name,
            expression=expression,
            description=description,
        )
        return single_result(_pick(created, _STORED_QUERY_FIELDS))

    async def list_stored_queries(
        self,
        *,
        limit: int | None = None,
        marker: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        if limit is not None:
            limit = clamp_limit(limit)
        response = await self._client.list_stored_queries(limit=limit, marker=marker, name=name)
        queries = response.get("value") or []
        items = [_pick(q, _STORED_QUERY_FIELDS) for q in queries if isinstance(q, dict)]
        return page_result(items, total=None, marker=_next_marker(response))

    async def show_stored_query(self, *, query_id: str) -> dict[str, Any]:
        query = await self._client.show_stored_query(query_id=query_id)
        if query is None:
            raise _not_found("stored query", query_id)
        return single_result(_pick(query, _STORED_QUERY_FIELDS))

    async def update_stored_query(
        self,
        *,
        query_id: str,
        name: str,
        expression: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        query = await self._client.show_stored_query(query_id=query_id)
        if query is None:
            raise _not_found("stored query", query_id)
        updated = await self._client.update_stored_query(
            query_id=query_id,
            name=name,
            expression=expression,
            description=description,
        )
        return single_result(_pick(updated, _STORED_QUERY_FIELDS))

    async def delete_stored_query(
        self,
        *,
        query_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        query = await self._client.show_stored_query(query_id=query_id)
        if query is None:
            raise _not_found("stored query", query_id)
        if not confirm:
            preview = _pick(query, _STORED_QUERY_FIELDS)
            return {
                "confirmation_required": True,
                "preview": preview,
                "message": (
                    "This operation is irreversible and will delete the stored query. "
                    "Call again with confirm=true to proceed."
                ),
            }
        assert_not_protected(
            {
                "id": str(query.get("id") or ""),
                "name": str(query.get("name") or ""),
                "tags": {},
            },
            tool_name="delete_stored_query",
        )
        await self._client.delete_stored_query(query_id=query_id)
        return {
            "query_id": query_id,
            "deleted": True,
            "hints": ["Verify with list_stored_queries."],
        }


def _not_found(kind: str, ref: str) -> McpToolError:
    return McpToolError(
        code="MCP_NOT_FOUND",
        message=f"{kind} '{ref}' not found.",
        hint=f"Run the matching list tool to see existing {kind}s.",
    )
