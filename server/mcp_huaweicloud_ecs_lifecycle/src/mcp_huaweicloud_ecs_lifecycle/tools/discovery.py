# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Discovery tools: read-only lookups that let the AI derive create arguments.

These exist so a user can say "open a cheap test box" and the AI can resolve
image_ref / flavor_ref / key_name on its own before calling create_server —
instead of the user filling in console-style forms by hand.
"""

from __future__ import annotations

from typing import Any

from huaweicloud_mcp_core.security import ToolRisk, guard

from mcp_huaweicloud_ecs_lifecycle.server import mcp
from mcp_huaweicloud_ecs_lifecycle.service.lifecycle_service import EcsLifecycleService


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def list_images(
    name: str | None = None,
    os_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search available images to pick an image_ref for create_server.

    Scenario: the user says "open a Ubuntu test box" — call this with
    name="Ubuntu" (substring, case-insensitive), pick the best match's id,
    and pass it as image_ref. Filter by os_type ("Linux"/"Windows") when the
    user names an OS family without a specific image.

    Args:
        name: Case-insensitive substring matched against the image name.
        os_type: "Linux" or "Windows" (case-insensitive exact match).
        limit: Max images returned, clamped to 1-100 (default 20).

    Returns:
        {"total", "count", "items": [{id, name, os_type, os_version, status,
        imagetype, min_disk, min_ram, visibility}, ...]}.
    """
    return await EcsLifecycleService().list_images(name=name, os_type=os_type, limit=limit)


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def list_flavors(
    vcpus: int | None = None,
    ram_gb: int | None = None,
    flavor_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search available flavors (specs) to pick a flavor_ref for create_server.

    Scenario: the user says "the smallest flavor is fine" — call this with
    vcpus=1, ram_gb=1, pick the smallest id, and pass it as flavor_ref. Omit
    filters to browse everything, e.g. when the user asks "what specs are
    available?". Pass flavor_id to check whether one specific flavor (e.g.
    one seen on an existing server) is orderable in this project — the list
    can hide restricted flavors, so an empty browse result does not prove
    the flavor is gone.

    Args:
        vcpus: Exact vCPU count to match (e.g. 1, 2, 4).
        ram_gb: Exact RAM in GiB to match (API stores MB; converted here).
        flavor_id: Exact flavor id to look up, e.g. "x1.1u.1g".
        limit: Max flavors returned, clamped to 1-100 (default 20).

    Returns:
        {"total", "count", "items": [{id, name, vcpus, ram (MB), disk (GB)}, ...]}.
    """
    return await EcsLifecycleService().list_flavors(
        vcpus=vcpus, ram_gb=ram_gb, flavor_id=flavor_id, limit=limit
    )


@mcp.tool()
@guard(risk=ToolRisk.READ)
async def list_keypairs(limit: int = 20) -> dict[str, Any]:
    """List existing SSH key pairs to pick a key_name for create_server.

    Scenario: the user wants key-based login — call this first, confirm a
    key exists, and pass its name as key_name. If none exists, fall back to
    admin_pass and say so in the preview.

    Args:
        limit: Max keypairs returned, clamped to 1-100 (default 20).

    Returns:
        {"total", "count", "items": [{name, fingerprint, type}, ...]}.
    """
    return await EcsLifecycleService().list_keypairs(limit=limit)
