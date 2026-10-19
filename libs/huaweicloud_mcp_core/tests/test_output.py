# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for output envelopes and token budget."""

from __future__ import annotations

from huaweicloud_mcp_core.output import (
    MAX_FIELD_LENGTH,
    clamp_limit,
    page_result,
    single_result,
)


def test_clamp_limit() -> None:
    assert clamp_limit(0) == 1
    assert clamp_limit(-5) == 1
    assert clamp_limit(20) == 20
    assert clamp_limit(999) == 100
    assert clamp_limit(100) == 100


def test_page_result_envelope() -> None:
    items = [{"id": "a"}, {"id": "b"}]
    result = page_result(items, total=7, marker="next-marker")
    assert result == {
        "items": items,
        "count": 2,
        "total": 7,
        "marker": "next-marker",
        "truncated": True,
    }


def test_page_result_defaults() -> None:
    result = page_result([])
    assert result["count"] == 0
    assert result["total"] == 0
    assert result["marker"] is None
    assert result["truncated"] is False


def test_page_result_truncates_long_fields() -> None:
    items = [{"log": "x" * (MAX_FIELD_LENGTH + 10)}]
    result = page_result(items)
    trimmed = result["items"][0]["log"]
    assert len(trimmed) == MAX_FIELD_LENGTH
    assert result["items"][0].get("_truncated") is True


def test_single_result_with_hints() -> None:
    result = single_result({"id": "a"}, hints=["next step"])
    assert result == {"id": "a", "hints": ["next step"]}


def test_single_result_truncation_marker() -> None:
    result = single_result({"huge": "y" * (MAX_FIELD_LENGTH + 5)})
    assert len(result["huge"]) == MAX_FIELD_LENGTH
    assert result["_truncated"] is True
