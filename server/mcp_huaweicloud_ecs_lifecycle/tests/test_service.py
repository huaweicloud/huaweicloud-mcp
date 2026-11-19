# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the ECS lifecycle service: filters, confirm protocol, guardrails."""

from __future__ import annotations

import base64
from typing import Any

import pytest
from huaweicloud_mcp_core.errors import McpToolError

from conftest import FakeLifecycleClient, register_server
from mcp_huaweicloud_ecs_lifecycle.service.lifecycle_service import EcsLifecycleService


@pytest.fixture
def service(fake_client: FakeLifecycleClient) -> EcsLifecycleService:
    return EcsLifecycleService(client=fake_client)  # type: ignore[arg-type]


async def test_list_servers_applies_filters(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    register_server(fake_client, "srv-1", name="web-1", status="ACTIVE")
    register_server(fake_client, "srv-2", name="web-2", status="SHUTOFF")
    register_server(fake_client, "srv-3", name="db-1", status="ACTIVE")

    result = await service.list_servers(name="web", status="active")

    # Filters are ANDed and status is case-insensitive: only srv-1 is both
    # named like web and ACTIVE (srv-2 is SHUTOFF, srv-3 is named db-1).
    assert result["total"] == 1
    assert result["count"] == 1
    assert [s["id"] for s in result["items"]] == ["srv-1"]
    assert set(result["items"][0]) == {
        "id",
        "name",
        "status",
        "flavor",
        "addresses",
        "tags",
        "created",
    }


async def test_list_servers_limit_caps_returned_not_total(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    register_server(fake_client, "srv-1")
    register_server(fake_client, "srv-2")
    register_server(fake_client, "srv-3")

    result = await service.list_servers(limit=1)

    assert result["total"] == 3
    assert result["count"] == 1
    assert result["items"][0]["id"] == "srv-1"


async def test_show_server_renames_zone_key(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    register_server(
        fake_client,
        "srv-1",
        name="web-1",
        description="app host",
        key_name="kp-1",
        security_groups=[{"name": "sg-1"}],
        image={"id": "img-1"},
        os_ext_a_zavailability_zone="cn-north-4a",
    )

    result = await service.show_server("srv-1")

    assert result["name"] == "web-1"
    assert result["description"] == "app host"
    assert result["availability_zone"] == "cn-north-4a"
    assert "os_ext_a_zavailability_zone" not in result
    assert set(result) == {
        "id",
        "name",
        "status",
        "description",
        "flavor",
        "image",
        "addresses",
        "security_groups",
        "key_name",
        "created",
        "tags",
        "availability_zone",
    }


async def test_show_job_returns_status_and_running_hint(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.jobs["job-1"] = {
        "job_id": "job-1",
        "status": "RUNNING",
        "job_type": "createServer",
        "entities": {"server_id": "srv-1"},
    }

    result = await service.show_job("job-1")

    assert result["status"] == "RUNNING"
    assert result["job_type"] == "createServer"
    assert "later" in result["hint"]


async def test_show_job_success_has_no_hint(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.jobs["job-1"] = {"job_id": "job-1", "status": "SUCCESS"}

    result = await service.show_job("job-1")

    assert result["status"] == "SUCCESS"
    assert "hint" not in result


async def test_create_server_preview_makes_no_side_effect(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    result = await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="GPSSD",
        admin_pass="Secret123!",
        count=2,
    )

    assert result["confirmation_required"] is True
    assert result["preview"]["operation"] == "create_server"
    assert result["preview"]["count"] == 2
    assert result["preview"]["billing"] == "prePaid (monthly/yearly)"
    assert result["preview"]["auth"] == "admin_pass"
    assert "confirm=true" in result["message"]
    assert fake_client.calls == []


async def test_create_server_confirm_executes(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    result = await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="GPSSD",
        key_name="kp-1",
        confirm=True,
    )

    assert result["job_id"] == "job-create-1"
    assert result["order_id"] == "order-1"
    assert result["server_ids"] == ["srv-new-1"]
    assert len(fake_client.calls) == 1
    method, kwargs = fake_client.calls[0]
    assert method == "create_pre_paid_server"
    assert kwargs["name"] == "web"
    assert kwargs["key_name"] == "kp-1"


async def test_create_server_manual_pay_hint(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    result = await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="GPSSD",
        admin_pass="Secret123!",
        confirm=True,
    )
    assert "manual" in result["hints"][0]

    auto = await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="GPSSD",
        admin_pass="Secret123!",
        is_auto_pay=True,
        confirm=True,
    )
    assert "automatically" in auto["hints"][0]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"count": 0},
        {"count": 101},
        {"admin_pass": None, "key_name": None},
        {"period_type": "week"},
        {"period_num": 10},
        {"period_type": "year", "period_num": 4},
    ],
)
async def test_create_server_rejects_invalid_args(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService, kwargs: dict[str, Any]
) -> None:
    base: dict[str, Any] = {
        "name": "web",
        "flavor_ref": "c7.large.2",
        "image_ref": "img-1",
        "vpc_id": "vpc-1",
        "subnet_id": "subnet-1",
        "root_volume_type": "GPSSD",
        "admin_pass": "Secret123!",
    }
    base.update(kwargs)
    with pytest.raises(McpToolError) as excinfo:
        await service.create_server(**base, confirm=True)
    assert excinfo.value.code == "MCP_INVALID_ARGS"
    assert fake_client.calls == []


async def test_create_on_demand_server_preview_and_confirm(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    preview = await service.create_on_demand_server(
        name="batch",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="SSD",
        admin_pass="Secret123!",
    )
    assert preview["confirmation_required"] is True
    assert preview["preview"]["billing"].startswith("postPaid")
    assert "per-second" in preview["message"]
    assert fake_client.calls == []

    result = await service.create_on_demand_server(
        name="batch",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        root_volume_type="SSD",
        key_name="kp-1",
        confirm=True,
    )
    assert result["job_id"] == "job-create-2"
    assert result["server_ids"] == ["srv-new-2"]
    assert [m for m, _ in fake_client.calls] == ["create_post_paid_server"]


def _seed_subnets(fake_client: FakeLifecycleClient) -> None:
    fake_client.subnets = [
        {"id": "subnet-b", "name": "zeta", "cidr": "10.1.0.0/24", "vpc_id": "vpc-b"},
        {"id": "subnet-a", "name": "alpha", "cidr": "10.0.0.0/24", "vpc_id": "vpc-a"},
    ]


async def test_default_reasons_explain_every_inferred_value(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    result = await service.create_server(
        name="web", flavor_ref="c7.large.2", image_ref="img-1", admin_pass="Secret123!"
    )

    reasons = result["preview"]["default_reasons"]
    # Every inferred field is explained, and the subnet note states the pick is
    # arbitrary rather than a recommendation.
    assert set(reasons) == {"vpc_id", "subnet_id", "root_volume_type"}
    assert "alphabetically" in reasons["subnet_id"]
    assert "not a recommendation" in reasons["subnet_id"]
    assert "2 usable subnet(s)" in reasons["subnet_id"]
    assert reasons["root_volume_type"] == "fixed default SSD"


async def test_default_reasons_omit_caller_supplied_values(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    result = await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-b",
        subnet_id="subnet-b",
        root_volume_type="GPSSD",
        admin_pass="Secret123!",
    )

    # Nothing was inferred, so there is nothing to explain.
    assert result["preview"]["defaults_applied"] == []
    assert result["preview"]["default_reasons"] == {}


async def test_default_reasons_cover_on_demand_preview(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    result = await service.create_on_demand_server(
        name="web", flavor_ref="c7.large.2", image_ref="img-1", key_name="kp-1"
    )

    reasons = result["preview"]["default_reasons"]
    assert set(reasons) == {"vpc_id", "subnet_id", "root_volume_type"}


async def test_default_subnet_honours_explicit_vpc(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    result = await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        vpc_id="vpc-b",
        admin_pass="Secret123!",
    )

    # "alpha" sorts before "zeta", but the caller pinned vpc-b, so the only
    # subnet in that VPC must win instead of the alphabetically first one.
    preview = result["preview"]
    assert preview["subnet_id"] == "subnet-b"
    assert preview["vpc_id"] == "vpc-b"
    assert preview["defaults_applied"] == ["subnet_id", "root_volume_type"]


async def test_default_subnet_explicit_vpc_without_subnets_raises(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    with pytest.raises(McpToolError) as excinfo:
        await service.create_server(
            name="web",
            flavor_ref="c7.large.2",
            image_ref="img-1",
            vpc_id="vpc-empty",
            admin_pass="Secret123!",
        )

    assert excinfo.value.code == "MCP_NOT_FOUND"
    assert "vpc-empty" in excinfo.value.message


async def test_default_subnet_skips_entry_missing_name_and_vpc(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)
    # A catalog entry with a null name sorts first on a name comparison
    # ("<anything>" > "") and carries no VPC link.
    fake_client.subnets.append({"id": "subnet-dirty", "name": None, "vpc_id": None})

    result = await service.create_server(
        name="web", flavor_ref="c7.large.2", image_ref="img-1", admin_pass="Secret123!"
    )

    assert result["preview"]["subnet_id"] == "subnet-a"
    assert result["preview"]["vpc_id"] == "vpc-a"


async def test_default_subnet_skips_entry_missing_id(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)
    fake_client.subnets.append({"id": None, "name": "aaa_x", "vpc_id": "vpc-x"})

    result = await service.create_server(
        name="web", flavor_ref="c7.large.2", image_ref="img-1", admin_pass="Secret123!"
    )

    assert result["preview"]["subnet_id"] == "subnet-a"
    assert result["preview"]["vpc_id"] == "vpc-a"


async def test_default_subnet_raises_when_every_entry_is_unusable(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.subnets = [
        {"id": "subnet-dirty", "name": None, "vpc_id": None},
        {"id": None, "name": "aaa_x", "vpc_id": "vpc-x"},
    ]

    with pytest.raises(McpToolError) as excinfo:
        await service.create_server(
            name="web", flavor_ref="c7.large.2", image_ref="img-1", admin_pass="Secret123!"
        )

    assert excinfo.value.code == "MCP_NOT_FOUND"
    assert "usable subnet" in excinfo.value.message


async def test_explicit_subnet_without_vpc_link_reports_catalog_gap(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.subnets = [{"id": "subnet-dirty", "name": "alpha", "vpc_id": None}]

    with pytest.raises(McpToolError) as excinfo:
        await service.create_server(
            name="web",
            flavor_ref="c7.large.2",
            image_ref="img-1",
            subnet_id="subnet-dirty",
            admin_pass="Secret123!",
        )

    # The subnet was found; the message must point at the missing VPC link
    # instead of claiming the id does not exist.
    assert excinfo.value.code == "MCP_NOT_FOUND"
    assert "no VPC link" in excinfo.value.message


async def test_create_server_preview_resolves_smart_defaults(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    result = await service.create_server(
        name="web", flavor_ref="c7.large.2", image_ref="img-1", admin_pass="Secret123!"
    )

    # Only the subnet catalog lookup happened — no create call.
    assert fake_client.calls == [("list_subnets", {})]
    preview = result["preview"]
    # The alphabetically first subnet by name wins.
    assert preview["subnet_id"] == "subnet-a"
    assert preview["vpc_id"] == "vpc-a"
    assert preview["root_volume_type"] == "SSD"
    assert preview["subnet"] == {"name": "alpha", "cidr": "10.0.0.0/24"}
    assert preview["defaults_applied"] == ["vpc_id", "subnet_id", "root_volume_type"]
    assert preview["public_ip"] == "none"


async def test_create_server_confirm_passes_resolved_defaults(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        key_name="kp-1",
        confirm=True,
    )

    assert [m for m, _ in fake_client.calls] == ["list_subnets", "create_pre_paid_server"]
    _, kwargs = fake_client.calls[1]
    assert kwargs["subnet_id"] == "subnet-a"
    assert kwargs["vpc_id"] == "vpc-a"
    assert kwargs["root_volume_type"] == "SSD"


async def test_create_server_derives_vpc_from_explicit_subnet(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    result = await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        subnet_id="subnet-b",
        admin_pass="Secret123!",
    )

    assert result["preview"]["vpc_id"] == "vpc-b"
    assert result["preview"]["defaults_applied"] == ["vpc_id", "root_volume_type"]
    assert result["preview"]["root_volume_type"] == "SSD"
    assert "subnet" not in result["preview"]


async def test_create_server_no_subnets_raises_not_found(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.create_server(
            name="web", flavor_ref="c7.large.2", image_ref="img-1", admin_pass="Secret123!"
        )
    assert excinfo.value.code == "MCP_NOT_FOUND"
    assert fake_client.calls == [("list_subnets", {})]


async def test_create_server_unknown_subnet_raises_not_found(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    with pytest.raises(McpToolError) as excinfo:
        await service.create_server(
            name="web",
            flavor_ref="c7.large.2",
            image_ref="img-1",
            subnet_id="subnet-x",
            admin_pass="Secret123!",
        )
    assert excinfo.value.code == "MCP_NOT_FOUND"
    assert "subnet-x" in excinfo.value.message
    assert [m for m, _ in fake_client.calls] == ["list_subnets"]


async def test_create_server_encodes_user_data(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    result = await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        user_data="#!/bin/bash\necho hello",
        key_name="kp-1",
        confirm=True,
    )

    _, kwargs = fake_client.calls[-1]
    assert kwargs["user_data"] == base64.b64encode(b"#!/bin/bash\necho hello").decode("ascii")
    assert "show_job" in result["hints"][1]


async def test_create_server_rejects_oversized_user_data(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.create_server(
            name="web",
            flavor_ref="c7.large.2",
            image_ref="img-1",
            user_data="x" * (33 * 1024),
            admin_pass="Secret123!",
        )
    assert excinfo.value.code == "MCP_INVALID_ARGS"
    assert fake_client.calls == []


async def test_create_server_validates_eip_bandwidth(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    for bad in (0, 1001):
        with pytest.raises(McpToolError) as excinfo:
            await service.create_server(
                name="web",
                flavor_ref="c7.large.2",
                image_ref="img-1",
                eip_bandwidth=bad,
                admin_pass="Secret123!",
            )
        assert excinfo.value.code == "MCP_INVALID_ARGS"
    assert fake_client.calls == []

    result = await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        eip_bandwidth=10,
        admin_pass="Secret123!",
    )
    assert result["preview"]["public_ip"] == "auto-assign 10 Mbit/s EIP (billed by traffic)"


async def test_create_server_passes_security_group_id(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    _seed_subnets(fake_client)

    preview = await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        security_group_id="sg-1",
        admin_pass="Secret123!",
    )
    assert preview["preview"]["security_group_id"] == "sg-1"

    await service.create_server(
        name="web",
        flavor_ref="c7.large.2",
        image_ref="img-1",
        security_group_id="sg-1",
        key_name="kp-1",
        confirm=True,
    )

    _, kwargs = fake_client.calls[-1]
    assert kwargs["security_group_id"] == "sg-1"


async def test_update_server_requires_at_least_one_change(
    service: EcsLifecycleService,
) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.update_server(server_id="srv-1")
    assert excinfo.value.code == "MCP_INVALID_ARGS"


async def test_update_server_preview_shows_current_vs_new(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    register_server(fake_client, "srv-1", name="web-1", description="old text")

    result = await service.update_server(server_id="srv-1", name="web-2", description="new text")

    assert result["confirmation_required"] is True
    preview = result["preview"]
    assert preview["server_id"] == "srv-1"
    assert preview["name"] == "web-1"
    assert preview["changes"] == {
        "name": {"current": "web-1", "new": "web-2"},
        "description": {"current": "old text", "new": "new text"},
    }
    assert fake_client.calls == [("list_all_servers", {})]


async def test_update_server_confirm_executes(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    register_server(fake_client, "srv-1", name="web-1")

    result = await service.update_server(server_id="srv-1", name="web-2", confirm=True)

    assert result["updated"] is True
    assert result["changes"] == {"name": "web-2"}
    assert [m for m, _ in fake_client.calls] == ["list_all_servers", "update_server"]


async def test_update_server_confirm_rejects_unknown_id(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.update_server(server_id="missing", name="x", confirm=True)
    assert excinfo.value.code == "MCP_NOT_FOUND"
    assert [m for m, _ in fake_client.calls] == ["list_all_servers"]


async def test_update_server_confirm_blocked_by_protection(
    fake_client: FakeLifecycleClient,
    service: EcsLifecycleService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_server(fake_client, "srv-1", name="web-1")
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_IDS", "srv-1")

    with pytest.raises(McpToolError) as excinfo:
        await service.update_server(server_id="srv-1", name="web-2", confirm=True)

    assert excinfo.value.code == "MCP_GUARDRAIL_BLOCKED"
    assert [m for m, _ in fake_client.calls] == ["list_all_servers"]


async def test_delete_servers_preview_lists_real_servers(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    register_server(fake_client, "srv-1", name="web-1", status="ACTIVE", tags=["team:a"])
    register_server(fake_client, "srv-2", name="web-2", status="SHUTOFF")

    result = await service.delete_servers(server_ids=["srv-1", "missing"])

    assert result["confirmation_required"] is True
    assert result["preview"]["servers"] == [
        {"id": "srv-1", "name": "web-1", "status": "ACTIVE", "tags": ["team:a"]}
    ]
    assert result["preview"]["not_found"] == ["missing"]
    assert result["preview"]["delete_volume"] is False
    assert "kept and detached" in result["preview"]["consequence"]
    assert "irreversible" in result["message"]
    assert fake_client.calls == [("list_all_servers", {})]


async def test_delete_servers_preview_consequence_for_destructive_flags(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    register_server(fake_client, "srv-1", name="web-1")

    result = await service.delete_servers(
        server_ids=["srv-1"], delete_volume=True, delete_publicip=True
    )

    assert "deleted together" in result["preview"]["consequence"]


async def test_delete_servers_confirm_executes(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    register_server(fake_client, "srv-1", name="web-1")
    register_server(fake_client, "srv-2", name="web-2")

    result = await service.delete_servers(server_ids=["srv-2", "srv-2", "srv-1"], confirm=True)

    assert result["job_id"] == "job-delete-1"
    assert result["server_ids"] == ["srv-2", "srv-1"]  # deduplicated, order kept
    assert [m for m, _ in fake_client.calls] == ["list_all_servers", "delete_servers"]
    _, kwargs = fake_client.calls[1]
    assert kwargs["server_ids"] == ["srv-2", "srv-1"]


async def test_delete_servers_confirm_rejects_unknown_ids(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    register_server(fake_client, "srv-1", name="web-1")

    with pytest.raises(McpToolError) as excinfo:
        await service.delete_servers(server_ids=["srv-1", "missing"], confirm=True)

    assert excinfo.value.code == "MCP_NOT_FOUND"
    assert "missing" in excinfo.value.message
    assert [m for m, _ in fake_client.calls] == ["list_all_servers"]


async def test_delete_servers_confirm_blocked_by_protection(
    fake_client: FakeLifecycleClient,
    service: EcsLifecycleService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_server(fake_client, "srv-1", name="web-1", tags=["env:prod"])
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_TAGS", "env:prod")

    with pytest.raises(McpToolError) as excinfo:
        await service.delete_servers(server_ids=["srv-1"], confirm=True)

    assert excinfo.value.code == "MCP_GUARDRAIL_BLOCKED"
    assert [m for m, _ in fake_client.calls] == ["list_all_servers"]


async def test_delete_servers_requires_ids(service: EcsLifecycleService) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_servers(server_ids=[])
    assert excinfo.value.code == "MCP_INVALID_ARGS"
