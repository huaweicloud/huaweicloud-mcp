"""Tests for the RC service layer (orchestration scenarios)."""

from __future__ import annotations

import pytest
from huaweicloud_mcp_core.errors import McpToolError

from conftest import (
    FakeRcClient,
    register_group,
    register_inventory_resource,
    register_provider,
    register_relation,
    register_resource,
    register_stored_query,
    register_tag,
)
from mcp_server_rc.service.resource_service import ResourceService


@pytest.fixture
def service(fake_client: FakeRcClient) -> ResourceService:
    return ResourceService(client=fake_client)  # type: ignore[arg-type]  # fake injection for tests


# -- run_query / list_providers ----------------------------------------------


async def test_run_query_returns_paginated_results(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_resource(fake_client, "ecs", type_="cloudservers", name="web-01", num=1)
    register_resource(fake_client, "vpc", type_="vpcs", name="vpc-01", num=1)
    result = await service.run_query(expression="SELECT * FROM resources")
    assert result["count"] == 2
    assert result["total"] == 2
    assert result["items"][0]["provider"] == "ecs"
    assert result["items"][1]["provider"] == "vpc"


async def test_run_query_default_limit_50(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    for i in range(80):
        register_resource(fake_client, "ecs", name=f"vm-{i}")
    result = await service.run_query(expression="SELECT * FROM resources")
    assert result["count"] == 50
    assert result["total"] == 80


async def test_run_query_limit_is_clamped(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    for i in range(5):
        register_resource(fake_client, "ecs", name=f"vm-{i}")
    result = await service.run_query(expression="SELECT * FROM resources", limit=2)
    assert result["count"] == 2
    assert result["total"] == 5


async def test_run_query_empty_results(service: ResourceService) -> None:
    result = await service.run_query(expression="SELECT * FROM resources WHERE 1=0")
    assert result["count"] == 0
    assert result["items"] == []


async def test_run_query_preserves_dynamic_alias_fields(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_resource(fake_client, "ecs", alias_name="web-01", custom_col="x")
    result = await service.run_query(expression="SELECT name AS alias_name FROM resources")
    item = result["items"][0]
    assert "alias_name" in item
    assert "custom_col" in item


async def test_run_query_drops_none_values(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_resource(fake_client, "ecs", missing=None)
    result = await service.run_query(expression="SELECT * FROM resources")
    item = result["items"][0]
    assert "missing" not in item
    assert "provider" in item


async def test_list_providers_returns_paginated_results(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_provider(fake_client, "ecs", display_name="Elastic Cloud Server")
    register_provider(fake_client, "vpc", display_name="Virtual Private Cloud")
    result = await service.list_providers()
    assert result["count"] == 2
    assert result["total"] == 2
    assert result["items"][0]["provider"] == "ecs"
    assert result["items"][0]["category_display_name"] == "Compute"
    assert fake_client.calls[-1] == (
        "list_providers",
        {"offset": None, "limit": None, "x_language": None},
    )


async def test_list_providers_passes_pagination(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_provider(fake_client, "ecs")
    await service.list_providers(offset=10, limit=50, x_language="zh-cn")
    assert fake_client.calls[-1] == (
        "list_providers",
        {"offset": 10, "limit": 50, "x_language": "zh-cn"},
    )


# -- resource inventory -------------------------------------------------------


async def test_list_all_resources_paginates(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_inventory_resource(fake_client, "r-1", name="web-01")
    register_inventory_resource(fake_client, "r-2", name="db-01")
    fake_client.next_marker = "marker-2"
    result = await service.list_all_resources(limit=10)
    assert result["count"] == 2
    assert result["marker"] == "marker-2"
    assert result["items"][0]["id"] == "r-1"
    assert result["items"][0]["provider"] == "ecs"


async def test_list_all_resources_limit_clamped(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_inventory_resource(fake_client, "r-1")
    result = await service.list_all_resources(limit=5000)
    assert fake_client.calls[-1][1]["limit"] == 100
    assert result["count"] == 1


async def test_list_all_resources_limit_omitted_uses_api_default(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_inventory_resource(fake_client, "r-1")
    await service.list_all_resources()
    assert fake_client.calls[-1][1]["limit"] is None


async def test_list_all_resources_field_whitelist(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_inventory_resource(fake_client, "r-1", extra_field="should_be_filtered")
    result = await service.list_all_resources()
    item = result["items"][0]
    assert "extra_field" not in item
    assert "id" in item
    assert "tags" in item


async def test_show_resource_detail_returns_single(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_inventory_resource(
        fake_client,
        "r-1",
        name="web-01",
        tags={"env": "prod"},
        properties={"os": "linux", "flavor": "s3.xlarge.2"},
    )
    result = await service.show_resource_detail(resource_id="r-1")
    assert result["id"] == "r-1"
    assert result["name"] == "web-01"
    assert result["tags"] == {"env": "prod"}
    assert result["properties"] == {"os": "linux", "flavor": "s3.xlarge.2"}


async def test_show_resource_detail_missing_raises(service: ResourceService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.show_resource_detail(resource_id="ghost")
    assert excinfo.value.code == "MCP_NOT_FOUND"
    assert "list tool" in (excinfo.value.hint or "")


async def test_list_all_tags_returns_paginated(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_tag(fake_client, "env", ["prod", "dev"])
    register_tag(fake_client, "team", ["platform"])
    result = await service.list_all_tags(limit=10)
    assert result["count"] == 2
    assert result["items"][0]["key"] == "env"
    assert result["items"][0]["value"] == ["prod", "dev"]


async def test_list_all_tags_limit_clamped(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_tag(fake_client, "env")
    result = await service.list_all_tags(limit=5000)
    assert fake_client.calls[-1][1]["limit"] == 100
    assert result["count"] == 1


async def test_list_all_tags_limit_omitted_uses_api_default(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_tag(fake_client, "env")
    await service.list_all_tags()
    assert fake_client.calls[-1][1]["limit"] is None


async def test_count_all_resources_returns_total(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_inventory_resource(fake_client, "r-1")
    register_inventory_resource(fake_client, "r-2")
    result = await service.count_all_resources(resource_type=["ecs.cloudservers"])
    assert result["total_count"] == 2
    assert fake_client.calls[-1] == (
        "count_all_resources",
        {
            "id_": None,
            "name": None,
            "group_id": None,
            "resource_type": ["ecs.cloudservers"],
            "region_id": None,
            "ep_id": None,
            "project_id": None,
            "tags": None,
        },
    )


async def test_count_all_resources_passes_group_id(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_inventory_resource(fake_client, "r-1")
    await service.count_all_resources(group_id="g-1")
    assert fake_client.calls[-1][1]["group_id"] == "g-1"


async def test_collect_resources_summary_whitelists_fields(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    fake_client.calls.clear()

    async def summary_as_body(**kwargs: str) -> dict[str, object]:
        fake_client.calls.append(("collect_all_resources_summary", dict(kwargs)))
        return {
            "body": [
                {
                    "provider": "obs",
                    "extra_field": "should_be_filtered",
                    "types": [
                        {
                            "type": "buckets",
                            "extra_type_field": "filtered",
                            "regions": [
                                {"region_id": "cn-north-4", "count": 5, "extra_region": "no"},
                                "not-a-dict",
                            ],
                        }
                    ],
                }
            ]
        }

    fake_client.collect_all_resources_summary = summary_as_body  # type: ignore[method-assign]
    result = await service.collect_resources_summary(name="web")
    assert result["count"] == 1
    item = result["items"][0]
    assert item["provider"] == "obs"
    assert "extra_field" not in item
    assert item["types"] == [
        {
            "type": "buckets",
            "regions": [{"region_id": "cn-north-4", "count": 5}],
        }
    ]


# -- resource groups -----------------------------------------------------------


async def test_create_resource_group_returns_group(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    result = await service.create_resource_group(group_name="web-grp", description="d")
    assert result["group_id"] == "group-web-grp"
    assert result["group_name"] == "web-grp"
    assert result["description"] == "d"


async def test_show_resource_group_returns_single(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_group(fake_client, "g-1", group_name="web")
    result = await service.show_resource_group(group_id="g-1")
    assert result["group_id"] == "g-1"
    assert result["group_name"] == "web"


async def test_show_resource_group_missing_raises(service: ResourceService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.show_resource_group(group_id="ghost")
    assert excinfo.value.code == "MCP_NOT_FOUND"


async def test_list_resource_groups_returns_paginated(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_group(fake_client, "g-1", group_name="web")
    register_group(fake_client, "g-2", group_name="db")
    result = await service.list_resource_groups(limit=10)
    assert result["count"] == 2
    assert result["items"][0]["group_id"] == "g-1"


async def test_update_resource_group_returns_updated(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_group(fake_client, "g-1", group_name="web")
    result = await service.update_resource_group(group_id="g-1", description="new-desc")
    assert result["group_id"] == "g-1"
    assert result["description"] == "new-desc"


async def test_update_resource_group_missing_raises(service: ResourceService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.update_resource_group(group_id="ghost", description="d")
    assert excinfo.value.code == "MCP_NOT_FOUND"


async def test_delete_group_without_confirm_returns_preview(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_group(fake_client, "g-1", group_name="web", description="d")
    result = await service.delete_resource_group(group_id="g-1")
    assert result["confirmation_required"] is True
    assert result["preview"]["group_id"] == "g-1"
    assert result["preview"]["group_name"] == "web"
    assert all(call[0] != "delete_resource_group" for call in fake_client.calls)


async def test_delete_group_with_confirm_deletes(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_group(fake_client, "g-1", group_name="web")
    result = await service.delete_resource_group(group_id="g-1", confirm=True)
    assert result["deleted"] is True
    assert fake_client.calls[-1] == ("delete_resource_group", {"group_id": "g-1"})
    assert "g-1" not in fake_client.groups


async def test_delete_group_missing_raises(service: ResourceService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_resource_group(group_id="ghost", confirm=True)
    assert excinfo.value.code == "MCP_NOT_FOUND"


async def test_delete_group_blocked_by_protection_rule(
    service: ResourceService,
    fake_client: FakeRcClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_NAMES", "prod-group")
    register_group(fake_client, "g-1", group_name="prod-group")
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_resource_group(group_id="g-1", confirm=True)
    assert excinfo.value.code == "MCP_GUARDRAIL_BLOCKED"
    assert all(call[0] != "delete_resource_group" for call in fake_client.calls)


async def test_add_resources_to_group_returns_resources(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_group(fake_client, "g-1", group_name="web")
    register_inventory_resource(fake_client, "r-1")
    register_inventory_resource(fake_client, "r-2")
    result = await service.add_resources_to_group(group_id="g-1", resource_ids=["r-1", "r-2"])
    assert result["count"] == 2
    assert result["items"][0]["id"] == "r-1"


async def test_add_resources_to_group_missing_group_raises(service: ResourceService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.add_resources_to_group(group_id="ghost", resource_ids=["r-1"])
    assert excinfo.value.code == "MCP_NOT_FOUND"


async def test_remove_resource_from_group_returns_removed(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_group(fake_client, "g-1", group_name="web")
    register_inventory_resource(fake_client, "r-1")
    result = await service.remove_resource_from_group(group_id="g-1", resource_id="r-1")
    assert result["id"] == "r-1"


async def test_remove_resource_from_group_missing_group_raises(service: ResourceService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.remove_resource_from_group(group_id="ghost", resource_id="r-1")
    assert excinfo.value.code == "MCP_NOT_FOUND"


# -- resource relations --------------------------------------------------------


async def test_show_resource_relations_returns_paginated(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_relation(fake_client, "r-1", "vpc-1", related_resource_type="vpc.vpcs")
    register_relation(fake_client, "r-1", "eip-1", related_resource_type="vpc.publicips")
    result = await service.show_resource_relations(resource_id="r-1", limit=10)
    assert result["count"] == 2
    assert result["items"][0]["resource_id"] == "r-1"
    assert result["items"][0]["related_resource_type"] == "vpc.vpcs"


async def test_show_resource_relations_limit_clamped(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_relation(fake_client, "r-1", "vpc-1")
    result = await service.show_resource_relations(resource_id="r-1", limit=5000)
    assert fake_client.calls[-1][1]["limit"] == 100
    assert result["count"] == 1


# -- stored queries -------------------------------------------------------------


async def test_create_stored_query_returns_query(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    result = await service.create_stored_query(name="q1", expression="SELECT 1", description="d")
    assert result["id"] == "query-q1"
    assert result["name"] == "q1"
    assert result["expression"] == "SELECT 1"


async def test_list_stored_queries_returns_paginated(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_stored_query(fake_client, "q-1", name="q1")
    register_stored_query(fake_client, "q-2", name="q2")
    result = await service.list_stored_queries(limit=10)
    assert result["count"] == 2
    assert result["items"][0]["id"] == "q-1"


async def test_show_stored_query_returns_single(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_stored_query(fake_client, "q-1", name="q1", expression="SELECT * FROM resources")
    result = await service.show_stored_query(query_id="q-1")
    assert result["id"] == "q-1"
    assert result["expression"] == "SELECT * FROM resources"


async def test_show_stored_query_missing_raises(service: ResourceService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.show_stored_query(query_id="ghost")
    assert excinfo.value.code == "MCP_NOT_FOUND"


async def test_update_stored_query_returns_updated(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_stored_query(fake_client, "q-1", name="q1", expression="SELECT 1")
    result = await service.update_stored_query(query_id="q-1", name="q2", expression="SELECT 2")
    assert result["id"] == "q-1"
    assert result["name"] == "q2"
    assert result["expression"] == "SELECT 2"


async def test_update_stored_query_missing_raises(service: ResourceService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.update_stored_query(query_id="ghost", name="q2", expression="SELECT 2")
    assert excinfo.value.code == "MCP_NOT_FOUND"


async def test_delete_query_without_confirm_returns_preview(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_stored_query(fake_client, "q-1", name="q1")
    result = await service.delete_stored_query(query_id="q-1")
    assert result["confirmation_required"] is True
    assert result["preview"]["id"] == "q-1"
    assert all(call[0] != "delete_stored_query" for call in fake_client.calls)


async def test_delete_query_with_confirm_deletes(
    service: ResourceService,
    fake_client: FakeRcClient,
) -> None:
    register_stored_query(fake_client, "q-1", name="q1")
    result = await service.delete_stored_query(query_id="q-1", confirm=True)
    assert result["deleted"] is True
    assert fake_client.calls[-1] == ("delete_stored_query", {"query_id": "q-1"})
    assert "q-1" not in fake_client.stored_queries


async def test_delete_query_missing_raises(service: ResourceService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_stored_query(query_id="ghost", confirm=True)
    assert excinfo.value.code == "MCP_NOT_FOUND"


async def test_delete_query_blocked_by_protection_rule(
    service: ResourceService,
    fake_client: FakeRcClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_NAMES", "prod-query")
    register_stored_query(fake_client, "q-1", name="prod-query")
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_stored_query(query_id="q-1", confirm=True)
    assert excinfo.value.code == "MCP_GUARDRAIL_BLOCKED"
    assert all(call[0] != "delete_stored_query" for call in fake_client.calls)
