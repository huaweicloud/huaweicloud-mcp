# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""MCP tools for ECS lifecycle operations (create/update/delete + read views)."""

from __future__ import annotations

from typing import Any

from huaweicloud_mcp_core.security import ToolRisk, guard

from mcp_server_ecs_lifecycle.server import mcp
from mcp_server_ecs_lifecycle.service.lifecycle_service import EcsLifecycleService


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def list_servers(
    name: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List ECS servers in the region with optional filters.

    Scenario: get an overview of existing servers before running any lifecycle
    operation (create / update / delete), e.g. to pick target server ids.

    Args:
        name: Case-insensitive substring filter on server name.
        status: Exact server status filter (ACTIVE, SHUTOFF, ERROR, ...).
        limit: Max servers to return, clamped to 1-100 (default 20). Output is
            capped after filtering; use the returned "total" to know how many
            matched.

    Returns:
        {"total", "count", "items": [{id, name, status, flavor, addresses, tags, created}]}.
    """
    return await EcsLifecycleService().list_servers(name=name, status=status, limit=limit)


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def show_server(server_id: str) -> dict[str, Any]:
    """Show full details of one ECS server by id.

    Scenario: inspect a single server (image, security groups, key pair, AZ,
    timestamps) before updating or deleting it.

    Args:
        server_id: The ECS server id.

    Returns:
        Whitelisted server detail fields: id, name, status, description, flavor,
        image, addresses, security_groups, key_name, availability_zone, created,
        updated, tags.
    """
    return await EcsLifecycleService().show_server(server_id)


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def show_job(job_id: str) -> dict[str, Any]:
    """Show the status of an asynchronous ECS job (create/delete servers).

    Scenario: after create_server / create_on_demand_server / delete_servers
    return a job_id, poll this tool until status becomes SUCCESS or FAIL.

    Args:
        job_id: The async job id returned by a create or delete tool.

    Returns:
        {status: SUCCESS|RUNNING|FAIL|INIT, job_id, error_code, fail_reason,
        job_type, entities, begin_time, end_time}.
    """
    return await EcsLifecycleService().show_job(job_id)


@mcp.tool()
@guard(risk=ToolRisk.WRITE)
async def create_server(
    name: str,
    flavor_ref: str,
    image_ref: str,
    vpc_id: str | None = None,
    subnet_id: str | None = None,
    root_volume_type: str | None = None,
    root_volume_size: int | None = None,
    user_data: str | None = None,
    security_group_id: str | None = None,
    eip_bandwidth: int | None = None,
    admin_pass: str | None = None,
    key_name: str | None = None,
    count: int = 1,
    availability_zone: str | None = None,
    description: str | None = None,
    period_type: str = "month",
    period_num: int = 1,
    is_auto_pay: bool = False,
    is_auto_renew: bool = False,
    is_auto_rename: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Create prepaid (monthly/yearly billed) ECS servers.

    Scenario: order one or more bill-per-month/year servers from a flavor and
    image. The user only names what matters (e.g. "open a small Ubuntu box");
    network and disk can be omitted — the server picks smart defaults and the
    preview shows exactly what was picked.

    With confirm=false the tool returns a preview of the order (no resources
    are created and nothing is charged). With confirm=true the servers are
    actually created and billing starts.

    Args:
        name: Server name (auto-suffixed when count > 1).
        flavor_ref: Flavor id, e.g. "c7.large.2" (find via list_flavors).
        image_ref: Image id (private or public image; find via list_images).
        vpc_id: VPC id the servers join; omit to use the default subnet's VPC.
        subnet_id: NIC subnet id; omit to let the server pick the default
            subnet — the preview shows the picked subnet name and CIDR.
        root_volume_type: System disk type, e.g. "SATA", "SAS", "SSD", "GPSSD";
            defaults to "SSD" when omitted.
        root_volume_size: System disk size in GB (cloud assigns a default when omitted).
        user_data: Startup script passed as-is (cloud-init); base64-encoded
            automatically, max 32 KB after encoding.
        security_group_id: Security group id; omit to use the VPC default
            security group.
        eip_bandwidth: Auto-assign a public IP with this bandwidth in Mbit/s
            (1-1000, billed by traffic); omit for no public IP. The EIP is
            released when the server is deleted.
        admin_pass: Login password (provide this or key_name).
        key_name: SSH key pair name (provide this or admin_pass; find via
            list_keypairs).
        count: Number of servers to create (1-100).
        availability_zone: Target AZ; cloud picks one when omitted.
        description: Server description.
        period_type: Billing period unit, "month" or "year".
        period_num: Billing period length: 1-9 for month, 1-3 for year.
        is_auto_pay: Pay the order automatically from balance (default false = manual payment).
        is_auto_renew: Auto-renew when the period ends (default false).
        is_auto_rename: Rename automatically on name conflict (default false).
        confirm: Must be true to actually create; false returns a preview only.

    Returns:
        Preview with confirmation_required=true (including defaults_applied)
        when confirm=false; otherwise {job_id, order_id, server_ids, hints}.
    """
    return await EcsLifecycleService().create_server(
        name=name,
        flavor_ref=flavor_ref,
        image_ref=image_ref,
        vpc_id=vpc_id,
        subnet_id=subnet_id,
        root_volume_type=root_volume_type,
        root_volume_size=root_volume_size,
        user_data=user_data,
        security_group_id=security_group_id,
        eip_bandwidth=eip_bandwidth,
        admin_pass=admin_pass,
        key_name=key_name,
        count=count,
        availability_zone=availability_zone,
        description=description,
        period_type=period_type,
        period_num=period_num,
        is_auto_pay=is_auto_pay,
        is_auto_renew=is_auto_renew,
        is_auto_rename=is_auto_rename,
        confirm=confirm,
    )


@mcp.tool()
@guard(risk=ToolRisk.WRITE)
async def create_on_demand_server(
    name: str,
    flavor_ref: str,
    image_ref: str,
    vpc_id: str | None = None,
    subnet_id: str | None = None,
    root_volume_type: str | None = None,
    root_volume_size: int | None = None,
    user_data: str | None = None,
    security_group_id: str | None = None,
    eip_bandwidth: int | None = None,
    admin_pass: str | None = None,
    key_name: str | None = None,
    count: int = 1,
    availability_zone: str | None = None,
    description: str | None = None,
    is_auto_rename: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Create on-demand (pay-per-use) ECS servers.

    Scenario: spin up servers billed per second while running, e.g. for
    short-lived workloads ("open a cheap test box for an hour"). Network and
    disk can be omitted — the server picks smart defaults and the preview
    shows exactly what was picked.

    With confirm=false the tool returns a preview of the request (no resources
    are created and nothing is charged). With confirm=true the servers are
    actually created and per-second billing starts immediately.

    Args:
        name: Server name (auto-suffixed when count > 1).
        flavor_ref: Flavor id, e.g. "c7.large.2" (find via list_flavors).
        image_ref: Image id (private or public image; find via list_images).
        vpc_id: VPC id the servers join; omit to use the default subnet's VPC.
        subnet_id: NIC subnet id; omit to let the server pick the default
            subnet — the preview shows the picked subnet name and CIDR.
        root_volume_type: System disk type, e.g. "SATA", "SAS", "SSD", "GPSSD";
            defaults to "SSD" when omitted.
        root_volume_size: System disk size in GB (cloud assigns a default when omitted).
        user_data: Startup script passed as-is (cloud-init); base64-encoded
            automatically, max 32 KB after encoding.
        security_group_id: Security group id; omit to use the VPC default
            security group.
        eip_bandwidth: Auto-assign a public IP with this bandwidth in Mbit/s
            (1-1000, billed by traffic); omit for no public IP. The EIP is
            released when the server is deleted.
        admin_pass: Login password (provide this or key_name).
        key_name: SSH key pair name (provide this or admin_pass; find via
            list_keypairs).
        count: Number of servers to create (1-100).
        availability_zone: Target AZ; cloud picks one when omitted.
        description: Server description.
        is_auto_rename: Rename automatically on name conflict (default false).
        confirm: Must be true to actually create; false returns a preview only.

    Returns:
        Preview with confirmation_required=true (including defaults_applied)
        when confirm=false; otherwise {job_id, server_ids, hints}.
    """
    return await EcsLifecycleService().create_on_demand_server(
        name=name,
        flavor_ref=flavor_ref,
        image_ref=image_ref,
        vpc_id=vpc_id,
        subnet_id=subnet_id,
        root_volume_type=root_volume_type,
        root_volume_size=root_volume_size,
        user_data=user_data,
        security_group_id=security_group_id,
        eip_bandwidth=eip_bandwidth,
        admin_pass=admin_pass,
        key_name=key_name,
        count=count,
        availability_zone=availability_zone,
        description=description,
        is_auto_rename=is_auto_rename,
        confirm=confirm,
    )


@mcp.tool()
@guard(risk=ToolRisk.WRITE)
async def update_server(
    server_id: str,
    name: str | None = None,
    description: str | None = None,
    hostname: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Update a server's name, description or hostname.

    Scenario: rename a server or change its description/hostname without
    touching anything else. At least one field to change must be provided.

    With confirm=false the tool returns a preview showing current vs new values
    (nothing is modified). With confirm=true the change is applied.

    Args:
        server_id: The ECS server id to update.
        name: New server name (1-64 chars).
        description: New description (0-85 chars).
        hostname: New hostname inside the OS.
        confirm: Must be true to actually modify; false returns a preview only.

    Returns:
        Preview with confirmation_required=true when confirm=false; otherwise
        {server_id, updated, changes, hints}.
    """
    return await EcsLifecycleService().update_server(
        server_id=server_id, name=name, description=description, hostname=hostname, confirm=confirm
    )


@mcp.tool()
@guard(risk=ToolRisk.DANGEROUS)
async def delete_servers(
    server_ids: list[str],
    delete_volume: bool = False,
    delete_publicip: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Delete one or more ECS servers permanently.

    Scenario: tear down servers that are no longer needed. This is
    irreversible — deleted servers cannot be recovered.

    With confirm=false the tool returns a preview listing the real servers
    (id/name/status/tags) about to be deleted, plus any ids that were not found
    (nothing is deleted). With confirm=true the servers are actually deleted.

    Args:
        server_ids: Ids of the servers to delete.
        delete_volume: Also DELETE attached data disks (default false = keep and detach them).
        delete_publicip: Also DELETE the bound EIP (default false = unbind and keep it).
        confirm: Must be true to actually delete; false returns a preview only.

    Returns:
        Preview with confirmation_required=true when confirm=false; otherwise
        {job_id, server_ids, hints}.
    """
    return await EcsLifecycleService().delete_servers(
        server_ids=server_ids,
        delete_volume=delete_volume,
        delete_publicip=delete_publicip,
        confirm=confirm,
    )
