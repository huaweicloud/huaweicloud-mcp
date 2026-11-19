# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Thin SDK wrapper for huaweicloudsdkecs. No business logic here."""

from __future__ import annotations

import os
from typing import Any

from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.credentials import CredentialScope, build_credentials

from huaweicloud_mcp_ecs_common import call_sdk, paginate


class EcsClient:
    """Async wrapper around the synchronous huaweicloudsdkecs client."""

    MAX_PAGE_SIZE = 1000

    def __init__(
        self,
        settings: McpSettings | None = None,
        sdk_client: Any = None,
    ) -> None:
        self._settings = settings or McpSettings.from_env()
        if sdk_client is not None:
            self._client = sdk_client
            return
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkecs.v2 import EcsClient as _SdkEcsClient
        from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion

        region_id = self._settings.region
        endpoint = self._settings.endpoint
        if endpoint and not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"
        if endpoint:
            # Explicit endpoint override wins over the SDK's static region map.
            sdk_region = Region(region_id, endpoint)
        else:
            try:
                sdk_region = EcsRegion.value_of(region_id)
            except KeyError:
                # Internal/beta regions are absent from the SDK's static map; every
                # map entry follows https://ecs.<region>.myhuaweicloud.com, so
                # synthesize on that pattern instead of failing at construction.
                sdk_region = Region(region_id, f"https://ecs.{region_id}.myhuaweicloud.com")
        from huaweicloudsdkcore.http.http_config import HttpConfig

        # Internal test regions (e.g. cn-southwest-242) present a self-signed
        # certificate over the VPN tunnel. Only skip TLS validation when the
        # operator explicitly lists this region; off by default and never applied
        # to unlisted regions, so public regions stay strictly verified.
        skip_regions = {
            r.strip()
            for r in os.getenv("HUAWEICLOUD_MCP_SKIP_SSL_VERIFY_REGIONS", "").split(",")
            if r.strip()
        }
        http_config = HttpConfig.get_default_config()
        if region_id in skip_regions:
            http_config.ignore_ssl_verification = True
        self._client = (
            _SdkEcsClient.new_builder()
            .with_credentials(build_credentials(CredentialScope.PROJECT, self._settings))
            .with_region(sdk_region)
            .with_http_config(http_config)
            .build()
        )

    async def list_all_servers(self) -> list[dict[str, Any]]:
        """Fetch every server in the region by paging through list-servers-details."""

        def _call() -> list[dict[str, Any]]:
            from huaweicloudsdkecs.v2.model.list_servers_details_request import (
                ListServersDetailsRequest,
            )

            offset = 1

            def fetch() -> Any:
                nonlocal offset
                request = ListServersDetailsRequest(limit=self.MAX_PAGE_SIZE, offset=offset)
                # Let SDK/transport exceptions surface raw to call_sdk so its retry
                # layer sees ServiceResponseException(429/5xx) and transport blips —
                # wrap_sdk_error in the client would pre-wrap them as McpToolError
                # and defeat the retry (it only re-wraps at the call_sdk boundary).
                response = self._client.list_servers_details(request)
                return response

            def advance(_batch: list[dict[str, Any]], _page: dict[str, Any]) -> str | None:
                nonlocal offset
                offset += 1
                # offset-style paging: return the next offset as the sentinel so the
                # dedupe guard sees a fresh value each page; the loop stops on an
                # empty/short page in paginate itself.
                return str(offset)

            return paginate(
                fetch,
                result_key="servers",
                page_size=self.MAX_PAGE_SIZE,
                advance=advance,
            )

        return await call_sdk(_call)
