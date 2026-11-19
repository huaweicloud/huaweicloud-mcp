# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the ECS service layer (orchestration scenarios)."""

from __future__ import annotations

import pytest

from conftest import FakeEcsClient, register_server
from mcp_huaweicloud_ecs_readonly.service.ecs_service import EcsService


@pytest.fixture
def service(fake_client: FakeEcsClient) -> EcsService:
    return EcsService(client=fake_client)  # type: ignore[arg-type]


@pytest.fixture
def mixed_region(fake_client: FakeEcsClient) -> FakeEcsClient:
    register_server(fake_client, "s-1", name="web-01")
    register_server(fake_client, "s-2", name="web-02")
    register_server(fake_client, "s-3", name="db-01")
    register_server(fake_client, "s-4", name="cache-01", status="SHUTOFF")
    register_server(fake_client, "s-5", name="etl-01", status="ERROR")
    register_server(
        fake_client,
        "s-6",
        name="big-01",
        flavor={"id": "c7.2xlarge.4", "name": "c7.2xlarge.4", "vcpus": 8, "ram": 32768},
    )
    register_server(
        fake_client,
        "s-7",
        name="edge-01",
        addresses={
            "net1": [
                {"addr": "114.116.1.1", "version": "4", "os_ext_ip_stype": "floating"},
                {"addr": "192.168.0.10", "version": "4", "os_ext_ip_stype": "fixed"},
            ]
        },
    )
    return fake_client


async def test_count_servers(service: EcsService, fake_client: FakeEcsClient) -> None:
    register_server(fake_client, "s-1")
    register_server(fake_client, "s-2")
    assert await service.count_servers() == {"count": 2}


async def test_count_servers_by_status(service: EcsService, mixed_region: FakeEcsClient) -> None:
    result = await service.count_servers_by_status()
    assert result["total"] == 7
    assert result["by_status"] == {"ACTIVE": 5, "SHUTOFF": 1, "ERROR": 1}


async def test_list_server_flavors(service: EcsService, mixed_region: FakeEcsClient) -> None:
    result = await service.list_server_flavors()
    assert result["total"] == 7
    top = result["flavors"][0]
    assert top["id"] == "c7.large.2"
    assert top["server_count"] == 6
    assert top["vcpus"] == 2
    assert top["ram"] == 4096
    second = result["flavors"][1]
    assert second["id"] == "c7.2xlarge.4"
    assert second["server_count"] == 1


async def test_analyze_server_resources_only_counts_active(
    service: EcsService, mixed_region: FakeEcsClient
) -> None:
    result = await service.analyze_server_resources()
    assert result == {
        "total_servers": 7,
        "active_servers": 5,
        "active_total_vcpus": 16,
        "active_total_ram_gb": 48.0,
    }


async def test_analyze_server_resources_empty(service: EcsService) -> None:
    result = await service.analyze_server_resources()
    assert result == {
        "total_servers": 0,
        "active_servers": 0,
        "active_total_vcpus": 0,
        "active_total_ram_gb": 0,
    }


async def test_analyze_server_ips(service: EcsService, mixed_region: FakeEcsClient) -> None:
    result = await service.analyze_server_ips()
    assert result == {"total_servers": 7, "public_ip_count": 1, "private_ip_count": 1}


async def test_list_servers_filters_by_name_and_status(
    service: EcsService, mixed_region: FakeEcsClient
) -> None:
    result = await service.list_servers(name="web", status="ACTIVE")
    assert result["total"] == 2
    assert [s["id"] for s in result["items"]] == ["s-1", "s-2"]
    assert all("flavor" in s and "addresses" in s and "tags" in s for s in result["items"])


async def test_list_servers_filters_by_flavor(
    service: EcsService, mixed_region: FakeEcsClient
) -> None:
    result = await service.list_servers(flavor="2xlarge")
    assert result["total"] == 1
    assert result["items"][0]["id"] == "s-6"


async def test_list_servers_limit_truncates(
    service: EcsService, mixed_region: FakeEcsClient
) -> None:
    result = await service.list_servers(limit=3)
    assert result["total"] == 7
    assert result["count"] == 3


async def test_list_servers_no_match(service: EcsService, mixed_region: FakeEcsClient) -> None:
    result = await service.list_servers(name="ghost")
    assert result["total"] == 0
    assert result["count"] == 0
    assert result["items"] == []


async def test_fetch_single_pull_for_all_scenarios(
    fake_client: FakeEcsClient,
) -> None:
    service = EcsService(client=fake_client)  # type: ignore[arg-type]
    register_server(fake_client, "s-1")
    await service.count_servers()
    await service.count_servers_by_status()
    await service.list_server_flavors()
    assert fake_client.calls == [
        ("list_all_servers", {}),
        ("list_all_servers", {}),
        ("list_all_servers", {}),
    ]
