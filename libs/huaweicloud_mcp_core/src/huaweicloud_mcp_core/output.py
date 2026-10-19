# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Output envelopes and token budget helpers."""

from __future__ import annotations

from typing import Any

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_FIELD_LENGTH = 2000


def clamp_limit(limit: int) -> int:
    return min(max(limit, 1), MAX_PAGE_SIZE)


def _truncate_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > MAX_FIELD_LENGTH:
            return value[:MAX_FIELD_LENGTH]
        return value
    if isinstance(value, list):
        return [_truncate_value(item) for item in value]
    if isinstance(value, tuple):
        return [_truncate_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        truncated = False
        for key, item in value.items():
            trimmed = _truncate_value(item)
            if isinstance(item, str) and isinstance(trimmed, str) and len(trimmed) < len(item):
                truncated = True
            result[key] = trimmed
        if truncated:
            result["_truncated"] = True
        return result
    return value


def page_result(
    items: list[dict[str, Any]],
    total: int | None = None,
    marker: str | None = None,
) -> dict[str, Any]:
    """Standard paginated envelope with token budget guards applied."""
    return {
        "items": [_truncate_value(item) for item in items],
        "count": len(items),
        "total": total if total is not None else len(items),
        "marker": marker,
        "truncated": total is not None and total > len(items),
    }


def single_result(
    obj: dict[str, Any],
    hints: list[str] | None = None,
) -> dict[str, Any]:
    """Single-object envelope: trimmed object plus optional follow-up hints."""
    result = _truncate_value(obj)
    if not isinstance(result, dict):
        result = {"result": result}
    if hints:
        result["hints"] = hints
    return result
