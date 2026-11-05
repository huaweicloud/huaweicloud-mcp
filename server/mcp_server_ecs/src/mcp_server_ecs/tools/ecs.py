# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Scenario tools for ECS usage reporting (read-only)."""

from __future__ import annotations

from typing import Any

from huaweicloud_mcp_core.security import ToolRisk, guard

from mcp_server_ecs.server import mcp
from mcp_server_ecs.service.ecs_service import EcsService


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def list_servers(
    name: str | None = None,
    status: str | None = None,
    flavor: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List ECS instances in the current region.

    Scenario: frontline staff need an inventory of cloud servers - what
    exists, its power state, and which flavor it runs on - optionally
    narrowed by name, status or flavor.

    Args:
        name: optional case-insensitive substring filter on server name.
        status: optional filter on server status (e.g. ACTIVE, SHUTOFF,
            ERROR); case-insensitive.
        flavor: optional case-insensitive substring filter on flavor id
            (e.g. "c7.large").
        limit: max servers to return, clamped to 1-100 (default 20). Use the
            returned "total" to know how many matched.

    Returns:
        Envelope with total (matched count), count (listed count) and
        items: each with id, name, status, flavor, addresses, tags,
        created.
    """
    return await EcsService().list_servers(name=name, status=status, flavor=flavor, limit=limit)


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def count_servers() -> dict[str, Any]:
    """Count all ECS instances in the current region.

    Scenario: user wants a quick "how many cloud servers do we have"
    number without listing every instance.

    Returns:
        {"count": <number of servers>}.
    """
    return await EcsService().count_servers()


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def count_servers_by_status() -> dict[str, Any]:
    """Count ECS instances grouped by power/status (ACTIVE, SHUTOFF...).

    Scenario: user wants to know how many machines are running vs stopped,
    e.g. to spot idle servers that can be shut down for savings.

    Returns:
        {"total": <server count>, "by_status": {"ACTIVE": n, ...}} sorted
        from most to least common.
    """
    return await EcsService().count_servers_by_status()


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def list_server_flavors() -> dict[str, Any]:
    """Inventory ECS instance types (flavors) with per-type server counts.

    Scenario: user wants to see which specifications the company uses and
    how many servers run each - useful for capacity review or
    standardization.

    Returns:
        {"total": <server count>, "flavors": [...]} where each flavor has
        id, name, vcpus, ram (MB) and server_count, sorted by count desc.
    """
    return await EcsService().list_server_flavors()


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def analyze_server_resources() -> dict[str, Any]:
    """Sum up vCPU and memory of all RUNNING ECS instances.

    Scenario: user asks "how much compute are we actually using" - only
    ACTIVE servers consume compute, so stopped ones are excluded.

    Returns:
        {"total_servers", "active_servers", "active_total_vcpus",
        "active_total_ram_gb"} (memory converted to GB).
    """
    return await EcsService().analyze_server_resources()


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def analyze_server_ips() -> dict[str, Any]:
    """Count public and private IPs in use across ECS instances.

    Scenario: user reviews network/IP usage - e.g. how many servers hold
    public IPs (cost/security exposure) vs private-only.

    Returns:
        {"total_servers", "public_ip_count", "private_ip_count"}.
    """
    return await EcsService().analyze_server_ips()
