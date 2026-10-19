"""Shared fixtures for the RC server tests."""

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


class FakeRcClient:
    """In-memory fake of the RcClient interface used by service tests."""

    def __init__(self) -> None:
        self.query_results: list[dict[str, Any]] = []
        self.providers: list[dict[str, Any]] = []
        self.resources: list[dict[str, Any]] = []
        self.tags: list[dict[str, Any]] = []
        self.groups: dict[str, dict[str, Any]] = {}
        self.stored_queries: dict[str, dict[str, Any]] = {}
        self.relations: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.next_marker: str | None = None

    def _record(self, name: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((name, kwargs))
        return {}

    async def run_query(self, *, expression: str) -> dict[str, Any]:
        self.calls.append(("run_query", {"expression": expression}))
        return {"query_info": None, "results": list(self.query_results)}

    async def list_providers(
        self, *, offset: int | None = None, limit: int | None = None, x_language: str | None = None
    ) -> dict[str, Any]:
        self.calls.append(
            ("list_providers", {"offset": offset, "limit": limit, "x_language": x_language})
        )
        return {"resource_providers": list(self.providers), "total_count": len(self.providers)}

    async def list_all_resources(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("list_all_resources", dict(kwargs)))
        items = list(self.resources)
        return {
            "resources": items[: kwargs.get("limit") or len(items)],
            "page_info": {"next_marker": self.next_marker},
        }

    async def show_resource_detail(self, *, resource_id: str) -> dict[str, Any] | None:
        self.calls.append(("show_resource_detail", {"resource_id": resource_id}))
        return next((r for r in self.resources if r.get("id") == resource_id), None)

    async def list_all_tags(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("list_all_tags", dict(kwargs)))
        items = list(self.tags)
        return {
            "tags": items[: kwargs.get("limit") or len(items)],
            "page_info": {"next_marker": self.next_marker},
        }

    async def count_all_resources(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("count_all_resources", dict(kwargs)))
        return {"total_count": len(self.resources)}

    async def collect_all_resources_summary(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("collect_all_resources_summary", dict(kwargs)))
        return {"body": []}

    async def create_resource_group(
        self, *, group_name: str, description: str | None = None
    ) -> dict[str, Any]:
        self.calls.append(
            ("create_resource_group", {"group_name": group_name, "description": description})
        )
        group: dict[str, Any] = {
            "group_id": f"group-{group_name}",
            "group_name": group_name,
            "description": description,
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z",
        }
        self.groups[group["group_id"]] = group
        return group

    async def delete_resource_group(self, *, group_id: str) -> dict[str, Any]:
        self.calls.append(("delete_resource_group", {"group_id": group_id}))
        self.groups.pop(group_id, None)
        return {}

    async def update_resource_group(
        self, *, group_id: str, description: str | None = None
    ) -> dict[str, Any]:
        self.calls.append(
            ("update_resource_group", {"group_id": group_id, "description": description})
        )
        group = self.groups.get(group_id)
        if group:
            group["description"] = description
        return dict(group or {})

    async def show_resource_group(self, *, group_id: str) -> dict[str, Any] | None:
        self.calls.append(("show_resource_group", {"group_id": group_id}))
        return self.groups.get(group_id)

    async def list_resource_groups(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("list_resource_groups", dict(kwargs)))
        items = list(self.groups.values())
        return {
            "resource_groups": items[: kwargs.get("limit") or len(items)],
            "page_info": {"next_marker": self.next_marker},
        }

    async def add_resources_to_group(
        self, *, group_id: str, resource_ids: list[str]
    ) -> dict[str, Any]:
        self.calls.append(
            ("add_resources_to_group", {"group_id": group_id, "resource_ids": resource_ids})
        )
        items = [r for r in self.resources if r.get("id") in resource_ids]
        return {"resources": items}

    async def remove_resource_from_group(
        self, *, group_id: str, resource_id: str
    ) -> dict[str, Any]:
        self.calls.append(
            ("remove_resource_from_group", {"group_id": group_id, "resource_id": resource_id})
        )
        return next((r for r in self.resources if r.get("id") == resource_id), {})

    async def show_resource_relations(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("show_resource_relations", dict(kwargs)))
        items = list(self.relations)
        return {
            "relations": items[: kwargs.get("limit") or len(items)],
            "page_info": {"next_marker": self.next_marker},
        }

    async def create_stored_query(
        self, *, name: str, expression: str, description: str | None = None
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "create_stored_query",
                {"name": name, "expression": expression, "description": description},
            )
        )
        query: dict[str, Any] = {
            "id": f"query-{name}",
            "name": name,
            "description": description,
            "expression": expression,
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z",
        }
        self.stored_queries[query["id"]] = query
        return query

    async def list_stored_queries(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("list_stored_queries", dict(kwargs)))
        items = list(self.stored_queries.values())
        return {
            "value": items[: kwargs.get("limit") or len(items)],
            "page_info": {"next_marker": self.next_marker},
        }

    async def show_stored_query(self, *, query_id: str) -> dict[str, Any] | None:
        self.calls.append(("show_stored_query", {"query_id": query_id}))
        return self.stored_queries.get(query_id)

    async def update_stored_query(
        self, *, query_id: str, name: str, expression: str, description: str | None = None
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "update_stored_query",
                {
                    "query_id": query_id,
                    "name": name,
                    "expression": expression,
                    "description": description,
                },
            )
        )
        query = self.stored_queries.get(query_id)
        if query:
            query["name"] = name
            query["expression"] = expression
            query["description"] = description
        return dict(query or {})

    async def delete_stored_query(self, *, query_id: str) -> dict[str, Any]:
        self.calls.append(("delete_stored_query", {"query_id": query_id}))
        self.stored_queries.pop(query_id, None)
        return {}


@pytest.fixture
def fake_client() -> FakeRcClient:
    return FakeRcClient()


def register_provider(
    client: FakeRcClient,
    provider: str,
    display_name: str | None = None,
    resource_types: list[str] | None = None,
    category_display_name: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "provider": provider,
        "display_name": display_name or provider,
        "category_display_name": category_display_name or "Compute",
        "resource_types": resource_types or [],
    }
    item.update(extra)
    client.providers.append(item)
    return item


def register_resource(
    client: FakeRcClient,
    provider: str,
    type_: str = "cloudservers",
    name: str | None = None,
    region_id: str = "cn-north-4",
    id_: str | None = None,
    num: int = 1,
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "provider": provider,
        "type": type_,
        "name": name or f"{provider}-{type_}",
        "region_id": region_id,
        "id": id_ or f"{provider}-{type_}-001",
        "num": num,
    }
    item.update(extra)
    client.query_results.append(item)
    return item


def register_inventory_resource(
    client: FakeRcClient,
    resource_id: str,
    provider: str = "ecs",
    type_: str = "cloudservers",
    name: str | None = None,
    region_id: str = "cn-north-4",
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": resource_id,
        "name": name or f"{provider}-{resource_id}",
        "provider": provider,
        "type": type_,
        "region_id": region_id,
        "project_id": "proj-1",
        "project_name": "default",
        "ep_id": "0",
        "ep_name": "default",
        "group_id": None,
        "purchase_model": "on_demand",
        "created": "2026-01-01T00:00:00Z",
        "updated": "2026-01-01T00:00:00Z",
        "provisioning_state": "Succeeded",
        "tags": {"env": "prod"},
        "state": "Normal",
    }
    item.update(extra)
    client.resources.append(item)
    return item


def register_tag(client: FakeRcClient, key: str, values: list[str] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"key": key, "value": values or ["v1"]}
    client.tags.append(item)
    return item


def register_group(
    client: FakeRcClient,
    group_id: str,
    group_name: str | None = None,
    description: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "group_id": group_id,
        "group_name": group_name or group_id,
        "description": description or "test group",
        "created": "2026-01-01T00:00:00Z",
        "updated": "2026-01-01T00:00:00Z",
    }
    item.update(extra)
    client.groups[group_id] = item
    return item


def register_relation(
    client: FakeRcClient,
    resource_id: str,
    related_resource_id: str,
    resource_type: str = "ecs.cloudservers",
    related_resource_type: str = "vpc.publicips",
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "related_resource_id": related_resource_id,
        "related_resource_type": related_resource_type,
    }
    item.update(extra)
    client.relations.append(item)
    return item


def register_stored_query(
    client: FakeRcClient,
    query_id: str,
    name: str | None = None,
    expression: str | None = None,
    description: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": query_id,
        "name": name or query_id,
        "description": description or "test query",
        "expression": expression or "SELECT * FROM resources",
        "created": "2026-01-01T00:00:00Z",
        "updated": "2026-01-01T00:00:00Z",
    }
    item.update(extra)
    client.stored_queries[query_id] = item
    return item
