"""Thin SDK wrapper for huaweicloudsdkrc. No business logic here.

SDK imports are lazy (inside the constructor and each method) so this module
can be imported without the SDK installed — this lets the service/tools test
layers inject fakes and run without `huaweicloudsdkrc` present. Real calls
(only reached when no fake is injected) require `uv sync` to install the SDK.
The SDK ships without type stubs; a mypy override in pyproject.toml silences
the resulting import-untyped diagnostics (spec §11.2).

The RC service is a *global* service: the region maps to the global endpoint
``https://rc.myhuaweicloud.com`` and authentication uses AK/SK signing only
(no project_id needed), so credentials use `CredentialScope.GLOBAL`.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.credentials import CredentialScope, build_credentials
from huaweicloud_mcp_core.errors import McpToolError, wrap_sdk_error
from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

_SKIP_ATTRS = {"local_vars_configuration", "discriminator", "swagger_types"}


def sdk_to_dict(obj: Any) -> Any:
    """Recursively convert an SDK response object into plain JSON-compatible data."""
    result: Any
    if obj is None or isinstance(obj, (str, int, float, bool)):
        result = obj
    elif isinstance(obj, bytes):
        result = obj.decode("utf-8", errors="replace")
    elif isinstance(obj, dict):
        result = {str(key): sdk_to_dict(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        result = [sdk_to_dict(item) for item in obj]
    elif hasattr(obj, "to_dict"):
        result = {str(key).lstrip("_"): sdk_to_dict(value) for key, value in obj.to_dict().items()}
    elif not hasattr(obj, "__dict__"):
        result = str(obj)
    else:
        result = {}
        for key, value in vars(obj).items():
            if key in _SKIP_ATTRS or key.startswith("__") or callable(value):
                continue
            result[key.lstrip("_")] = sdk_to_dict(value)
    return result


def _not_found(exc: ServiceResponseException) -> bool:
    return bool(exc.status_code == 404)


_PERMISSION_HINT = (
    "The AK/SK has no permission for this RC action. Grant the required IAM "
    "policy (e.g. ResourceCenter ReadOnlyAccess/FullAccess or the specific "
    "action) to the user and retry."
)


def _is_permission_error(err: McpToolError) -> bool:
    message = err.message or ""
    return "not authorized" in message or "no identity-based policy" in message


def _wrap_error(exc: ServiceResponseException) -> McpToolError:
    err = wrap_sdk_error(exc)
    if _is_permission_error(err):
        err.hint = _PERMISSION_HINT
    return err


class RcClient:
    """Async wrapper around the synchronous huaweicloudsdkrc client."""

    def __init__(
        self,
        settings: McpSettings | None = None,
        sdk_client: Any = None,
    ) -> None:
        self._settings = settings or McpSettings.from_env(require_credentials=False)
        if not self._settings.access_key or not self._settings.secret_key:
            raise McpToolError(
                code="MCP_INVALID_ARGS",
                message=(
                    "Missing required environment variables: "
                    "HUAWEICLOUD_ACCESS_KEY, HUAWEICLOUD_SECRET_KEY."
                ),
                hint=(
                    "Export HUAWEICLOUD_ACCESS_KEY and HUAWEICLOUD_SECRET_KEY "
                    "(see the Configuration section of the README). RC is a global "
                    "service and does not require HUAWEICLOUD_REGION."
                ),
            )
        if sdk_client is not None:
            self._client = sdk_client
        else:
            from huaweicloudsdkrc.v1 import RcClient as _SdkRcClient
            from huaweicloudsdkrc.v1.region.rc_region import RcRegion

            self._client = (
                _SdkRcClient.new_builder()
                .with_credentials(build_credentials(CredentialScope.GLOBAL, self._settings))
                .with_region(RcRegion.CN_NORTH_4)
                .build()
            )

    # -- resource list -------------------------------------------------

    async def list_all_resources(
        self,
        *,
        region_id: str | None = None,
        ep_id: str | None = None,
        resource_type: str | None = None,
        limit: int | None = None,
        marker: str | None = None,
        id_: str | None = None,
        group_id: str | None = None,
        name: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.list_all_resources_request import ListAllResourcesRequest

            request = ListAllResourcesRequest(
                region_id=region_id,
                ep_id=ep_id,
                type=resource_type,
                limit=limit,
                marker=marker,
                id=id_,
                group_id=group_id,
                name=name,
                tags=tags,
            )
            try:
                response = self._client.list_all_resources(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def show_resource_detail(self, *, resource_id: str) -> dict[str, Any] | None:
        def _call() -> dict[str, Any] | None:
            from huaweicloudsdkrc.v1.model.show_resource_detail_request import (
                ShowResourceDetailRequest,
            )

            request = ShowResourceDetailRequest(resource_id=resource_id)
            try:
                response = self._client.show_resource_detail(request)
            except ServiceResponseException as exc:
                if _not_found(exc):
                    return None
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def list_all_tags(
        self,
        *,
        key: str | None = None,
        marker: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.list_all_tags_request import ListAllTagsRequest

            request = ListAllTagsRequest(key=key, marker=marker, limit=limit)
            try:
                response = self._client.list_all_tags(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def count_all_resources(
        self,
        *,
        id_: str | None = None,
        name: str | None = None,
        group_id: str | None = None,
        resource_type: list[str] | None = None,
        region_id: list[str] | None = None,
        ep_id: list[str] | None = None,
        project_id: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.count_all_resources_request import (
                CountAllResourcesRequest,
            )

            request = CountAllResourcesRequest(
                id=id_,
                name=name,
                type=resource_type,
                region_id=region_id,
                ep_id=ep_id,
                project_id=project_id,
                tags=tags,
            )
            if group_id is not None and "group_id" in getattr(
                CountAllResourcesRequest, "openapi_types", {}
            ):
                request.group_id = group_id
            try:
                response = self._client.count_all_resources(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def collect_all_resources_summary(
        self,
        *,
        name: str | None = None,
        resource_type: list[str] | None = None,
        region_id: list[str] | None = None,
        ep_id: list[str] | None = None,
        project_id: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.collect_all_resources_summary_request import (
                CollectAllResourcesSummaryRequest,
            )

            request = CollectAllResourcesSummaryRequest(
                name=name,
                type=resource_type,
                region_id=region_id,
                ep_id=ep_id,
                project_id=project_id,
                tags=tags,
            )
            try:
                response = self._client.collect_all_resources_summary(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def list_providers(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
        x_language: str | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.list_all_providers_request import ListAllProvidersRequest

            request = ListAllProvidersRequest(
                offset=offset,
                limit=limit,
                x_language=x_language,
            )
            try:
                response = self._client.list_all_providers(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    # -- resource groups ----------------------------------------------------

    async def create_resource_group(
        self,
        *,
        group_name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.create_resource_group_request import (
                CreateResourceGroupRequest,
            )
            from huaweicloudsdkrc.v1.model.generic_resource_group_request_body import (
                GenericResourceGroupRequestBody,
            )

            body = GenericResourceGroupRequestBody(group_name=group_name, description=description)
            request = CreateResourceGroupRequest(body=body)
            try:
                response = self._client.create_resource_group(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def delete_resource_group(self, *, group_id: str) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.delete_resource_group_request import (
                DeleteResourceGroupRequest,
            )

            request = DeleteResourceGroupRequest(group_id=group_id)
            try:
                response = self._client.delete_resource_group(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def update_resource_group(
        self,
        *,
        group_id: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.update_resource_group_request import (
                UpdateResourceGroupRequest,
            )
            from huaweicloudsdkrc.v1.model.update_resource_group_request_body import (
                UpdateResourceGroupRequestBody,
            )

            body = UpdateResourceGroupRequestBody(description=description)
            request = UpdateResourceGroupRequest(group_id=group_id, body=body)
            try:
                response = self._client.update_resource_group(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def show_resource_group(self, *, group_id: str) -> dict[str, Any] | None:
        def _call() -> dict[str, Any] | None:
            from huaweicloudsdkrc.v1.model.show_resource_group_request import (
                ShowResourceGroupRequest,
            )

            request = ShowResourceGroupRequest(group_id=group_id)
            try:
                response = self._client.show_resource_group(request)
            except ServiceResponseException as exc:
                if _not_found(exc):
                    return None
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def list_resource_groups(
        self,
        *,
        limit: int | None = None,
        marker: str | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.list_resource_groups_request import (
                ListResourceGroupsRequest,
            )

            request = ListResourceGroupsRequest(limit=limit, marker=marker)
            try:
                response = self._client.list_resource_groups(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def add_resources_to_group(
        self,
        *,
        group_id: str,
        resource_ids: list[str],
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.add_resources_request_body import AddResourcesRequestBody
            from huaweicloudsdkrc.v1.model.add_resources_to_group_request import (
                AddResourcesToGroupRequest,
            )

            body = AddResourcesRequestBody(resource_ids=resource_ids)
            request = AddResourcesToGroupRequest(group_id=group_id, body=body)
            try:
                response = self._client.add_resources_to_group(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def remove_resource_from_group(
        self,
        *,
        group_id: str,
        resource_id: str,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.remove_resource_from_group_request import (
                RemoveResourceFromGroupRequest,
            )

            request = RemoveResourceFromGroupRequest(group_id=group_id, resource_id=resource_id)
            try:
                response = self._client.remove_resource_from_group(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    # -- resource relationships --------------------------------------------------

    async def show_resource_relations(
        self,
        *,
        resource_id: str,
        related_resource_id: str | None = None,
        related_resource_type: str | None = None,
        limit: int | None = None,
        marker: str | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.show_resource_relations_request import (
                ShowResourceRelationsRequest,
            )

            request = ShowResourceRelationsRequest(
                resource_id=resource_id,
                related_resource_id=related_resource_id,
                related_resource_type=related_resource_type,
                limit=limit,
                marker=marker,
            )
            try:
                response = self._client.show_resource_relations(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    # -- advanced queries ------------------------------------------------------

    async def create_stored_query(
        self,
        *,
        name: str,
        expression: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.create_stored_query_request import (
                CreateStoredQueryRequest,
            )
            from huaweicloudsdkrc.v1.model.stored_query_request_body import StoredQueryRequestBody

            body = StoredQueryRequestBody(name=name, description=description, expression=expression)
            request = CreateStoredQueryRequest(body=body)
            try:
                response = self._client.create_stored_query(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def list_stored_queries(
        self,
        *,
        limit: int | None = None,
        marker: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.list_stored_queries_request import (
                ListStoredQueriesRequest,
            )

            request = ListStoredQueriesRequest(limit=limit, marker=marker, name=name)
            try:
                response = self._client.list_stored_queries(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def show_stored_query(self, *, query_id: str) -> dict[str, Any] | None:
        def _call() -> dict[str, Any] | None:
            from huaweicloudsdkrc.v1.model.show_stored_query_request import ShowStoredQueryRequest

            request = ShowStoredQueryRequest(query_id=query_id)
            try:
                response = self._client.show_stored_query(request)
            except ServiceResponseException as exc:
                if _not_found(exc):
                    return None
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def update_stored_query(
        self,
        *,
        query_id: str,
        name: str,
        expression: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.stored_query_request_body import StoredQueryRequestBody
            from huaweicloudsdkrc.v1.model.update_stored_query_request import (
                UpdateStoredQueryRequest,
            )

            body = StoredQueryRequestBody(name=name, description=description, expression=expression)
            request = UpdateStoredQueryRequest(query_id=query_id, body=body)
            try:
                response = self._client.update_stored_query(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def delete_stored_query(self, *, query_id: str) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.delete_stored_query_request import (
                DeleteStoredQueryRequest,
            )

            request = DeleteStoredQueryRequest(query_id=query_id)
            try:
                response = self._client.delete_stored_query(request)
            except ServiceResponseException as exc:
                raise _wrap_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)

    async def run_query(self, *, expression: str) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkrc.v1.model.query_run_request_body import QueryRunRequestBody
            from huaweicloudsdkrc.v1.model.run_query_request import RunQueryRequest

            body = QueryRunRequestBody(expression=expression)
            request = RunQueryRequest(body=body)
            try:
                response = self._client.run_query(request)
            except ServiceResponseException as exc:
                err = _wrap_error(exc)
                if err.hint is None and exc.status_code >= 500:
                    err.hint = (
                        "The RC service failed to execute the query. Check the "
                        "ResourceQL syntax and retry with a simpler expression."
                    )
                raise err from exc
            return cast(dict[str, Any], sdk_to_dict(response))

        return await asyncio.to_thread(_call)
