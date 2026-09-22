# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the unified error model."""

from __future__ import annotations

import pytest

from huaweicloud_mcp_core.errors import McpToolError, wrap_sdk_error


def test_to_dict_full_shape() -> None:
    error = McpToolError(
        code="Ecs.0003",
        message="bad state",
        request_id="req-1",
        doc_url="https://example.com/doc",
        hint="check status",
    )
    payload = error.to_dict()
    assert payload == {
        "error": {
            "code": "Ecs.0003",
            "message": "bad state",
            "request_id": "req-1",
            "doc_url": "https://example.com/doc",
            "hint": "check status",
        }
    }


def test_to_dict_minimal_has_default_hint() -> None:
    payload = McpToolError("MCP_NOT_FOUND", "gone").to_dict()
    assert payload["error"]["code"] == "MCP_NOT_FOUND"
    assert "hint" in payload["error"]
    assert "request_id" not in payload["error"]


def test_wrap_generic_exception() -> None:
    wrapped = wrap_sdk_error(ValueError("boom"))
    assert wrapped.code == "MCP_SDK_ERROR"
    assert "boom" in wrapped.message


def test_wrap_service_response_exception() -> None:
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    try:
        exc = ServiceResponseException(
            status_code=404, request_id="req-9", error_code="RFS.1234", error_msg="not found"
        )
    except TypeError:
        pytest.skip("SDK exception signature differs")
    wrapped = wrap_sdk_error(exc)
    assert wrapped.code == "RFS.1234"
    assert wrapped.request_id == "req-9"
    assert "not found" in wrapped.message


def test_wrap_service_response_exception_without_error_code() -> None:
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    try:
        exc = ServiceResponseException(
            status_code=500, request_id=None, error_code=None, error_msg=None
        )
    except TypeError:
        pytest.skip("SDK exception signature differs")
    wrapped = wrap_sdk_error(exc)
    assert wrapped.code == "HTTP_500"
