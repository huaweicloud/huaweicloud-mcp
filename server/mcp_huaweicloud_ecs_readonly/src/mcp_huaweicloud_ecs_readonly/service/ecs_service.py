# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Service layer: ECS usage-report scenarios (count, flavors, power state, CPU/memory, IPs)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from huaweicloud_mcp_core.output import clamp_limit, page_result

from mcp_huaweicloud_ecs_readonly.client.ecs_client import EcsClient

_SERVER_FIELDS = (
    "id",
    "name",
    "status",
    "flavor",
    "addresses",
    "tags",
    "created",
)

_FLAVOR_FIELDS = ("id", "name", "vcpus", "ram")


def _pick(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in fields if source.get(key) is not None}


def _ip_stats(servers: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate public/private IP usage across servers."""
    public_ips: list[str] = []
    private_ips = 0
    for server in servers:
        for network in (server.get("addresses") or {}).values():
            for addr in network:
                ip = str(addr.get("addr") or "")
                if not ip:
                    continue
                if str(addr.get("os_ext_ip_stype") or "") == "fixed":
                    private_ips += 1
                elif ":" not in ip:
                    public_ips.append(ip)
    return {
        "public_ip_count": len(public_ips),
        "private_ip_count": private_ips,
    }


class EcsService:
    """Scenario orchestration for ECS usage reporting."""

    def __init__(self, client: EcsClient | None = None) -> None:
        self._client = client or EcsClient()

    async def list_servers(
        self,
        *,
        name: str | None = None,
        status: str | None = None,
        flavor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        servers = await self._fetch(name=name, status=status, flavor=flavor)
        items = [_pick(server, _SERVER_FIELDS) for server in servers]
        total = len(items)
        limit = clamp_limit(limit)
        return page_result(items[:limit], total=total)

    async def count_servers(self) -> dict[str, Any]:
        servers = await self._fetch()
        return {"count": len(servers)}

    async def count_servers_by_status(self) -> dict[str, Any]:
        servers = await self._fetch()
        counts = Counter(str(server.get("status") or "UNKNOWN") for server in servers)
        return {"total": len(servers), "by_status": dict(counts.most_common())}

    async def list_server_flavors(self) -> dict[str, Any]:
        servers = await self._fetch()
        flavor_count: Counter[str] = Counter()
        flavor_meta: dict[str, dict[str, Any]] = {}
        for server in servers:
            flavor = server.get("flavor") or {}
            flavor_id = str(flavor.get("id") or "UNKNOWN")
            flavor_count[flavor_id] += 1
            if flavor_id not in flavor_meta:
                flavor_meta[flavor_id] = _pick(flavor, _FLAVOR_FIELDS)
        return {
            "total": len(servers),
            "flavors": [
                {**flavor_meta[fid], "server_count": count}
                for fid, count in flavor_count.most_common()
            ],
        }

    async def analyze_server_resources(self) -> dict[str, Any]:
        servers = await self._fetch()
        total_vcpus = 0
        total_ram_mb = 0
        active = 0
        for server in servers:
            if str(server.get("status") or "") == "ACTIVE":
                active += 1
                flavor = server.get("flavor") or {}
                total_vcpus += int(flavor.get("vcpus") or 0)
                total_ram_mb += int(flavor.get("ram") or 0)
        return {
            "total_servers": len(servers),
            "active_servers": active,
            "active_total_vcpus": total_vcpus,
            "active_total_ram_gb": round(total_ram_mb / 1024, 1),
        }

    async def analyze_server_ips(self) -> dict[str, Any]:
        servers = await self._fetch()
        stats = _ip_stats(servers)
        return {"total_servers": len(servers), **stats}

    async def _fetch(
        self,
        *,
        name: str | None = None,
        status: str | None = None,
        flavor: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all servers once, then apply in-memory filters (SDK supports them too,
        but a single full fetch keeps the six scenarios consistent and cache-friendly)."""
        servers = await self._client.list_all_servers()
        if status:
            wanted = status.upper()
            servers = [s for s in servers if str(s.get("status") or "").upper() == wanted]
        if flavor:
            wanted = flavor.lower()
            servers = [
                s for s in servers if wanted in str((s.get("flavor") or {}).get("id") or "").lower()
            ]
        if name:
            wanted = name.lower()
            servers = [s for s in servers if wanted in str(s.get("name") or "").lower()]
        return servers
