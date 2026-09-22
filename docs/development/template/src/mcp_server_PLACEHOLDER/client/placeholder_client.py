# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Thin SDK wrapper for huaweicloudsdkPLACEHOLDER. No business logic here."""

from __future__ import annotations

import asyncio
from typing import Any

from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException
# from huaweicloudsdkPLACEHOLDER.v1 import PlaceholderClient as _SdkPlaceholderClient
# from huaweicloudsdkPLACEHOLDER.v1.region.placeholder_region import PlaceholderRegion

from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.credentials import CredentialScope, build_credentials
from huaweicloud_mcp_core.errors import wrap_sdk_error

_SKIP_ATTRS = {"local_vars_configuration", "discriminator", "swagger_types"}


def sdk_to_dict(obj: Any) -> Any:
    """Recursively convert an SDK response object into plain JSON-compatible data."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(key): sdk_to_dict(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sdk_to_dict(item) for item in obj]
    result: dict[str, Any] = {}
    for key, value in vars(obj).items():
        if key in _SKIP_ATTRS or key.startswith("__") or callable(value):
            continue
        result[key.lstrip("_")] = sdk_to_dict(value)
    return result


class PlaceholderClient:
    """Async wrapper around the synchronous huaweicloudsdkPLACEHOLDER client."""

    def __init__(
        self,
        settings: McpSettings | None = None,
        sdk_client: Any = None,
    ) -> None:
        self._settings = settings or McpSettings.from_env()
        if sdk_client is not None:
            self._client = sdk_client
        else:
            # self._client = (
            #     _SdkPlaceholderClient.new_builder()
            #     .with_credentials(build_credentials(CredentialScope.PROJECT, self._settings))
            #     .with_region(PlaceholderRegion.value_of(self._settings.region))
            #     .build()
            # )
            raise NotImplementedError("Replace PLACEHOLDER SDK imports and client construction.")

    async def list_resources(self, *, limit: int, marker: str | None) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            # request = ListResourcesRequest(limit=limit, marker=marker)
            # return sdk_to_dict(self._client.list_resources(request))
            raise NotImplementedError

        return await asyncio.to_thread(_call)

    async def get_resource(self, resource_id: str) -> dict[str, Any] | None:
        def _call() -> dict[str, Any] | None:
            # request = GetResourceRequest(resource_id=resource_id)
            # try:
            #     response = self._client.get_resource(request)
            # except ServiceResponseException as exc:
            #     if exc.status_code == 404:
            #         return None
            #     raise wrap_sdk_error(exc) from exc
            # return sdk_to_dict(response)
            raise NotImplementedError

        return await asyncio.to_thread(_call)

    async def delete_resource(self, *, resource_id: str) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            # request = DeleteResourceRequest(resource_id=resource_id)
            # return sdk_to_dict(self._client.delete_resource(request))
            raise NotImplementedError

        return await asyncio.to_thread(_call)
