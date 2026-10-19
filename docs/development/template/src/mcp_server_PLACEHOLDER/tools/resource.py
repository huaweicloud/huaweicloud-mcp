# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Scenario tools for PLACEHOLDER resources."""

from __future__ import annotations

from typing import Any

from huaweicloud_mcp_core.security import ToolRisk, guard

from mcp_server_PLACEHOLDER.server import mcp
from mcp_server_PLACEHOLDER.service.resource_service import ResourceService


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def list_resources(name: str | None = None, limit: int = 20, marker: str | None = None) -> dict[str, Any]:
    """List PLACEHOLDER resources in the current region.

    Scenario: user wants an inventory of resources — what exists and its
    current status.

    Args:
        name: optional case-insensitive substring filter on resource name.
        limit: max resources to return, 1-100 (default 20).
        marker: pagination marker returned by a previous call.

    Returns:
        Paginated envelope with items (id, name, status, ...).
    """
    return await ResourceService().list_resources(name=name, limit=limit, marker=marker)


@mcp.tool()
@guard(risk=ToolRisk.DANGEROUS)
async def delete_resource(
    resource_id: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Delete a PLACEHOLDER resource (irreversible).

    Scenario: user wants to tear down a resource. With confirm=false the tool
    returns a preview; call again with confirm=true to actually delete.

    Args:
        resource_id: resource UUID.
        confirm: must be explicitly true to execute; false returns a preview.
    """
    return await ResourceService().delete_resource(resource_id=resource_id, confirm=confirm)
