# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the shared ECS utilities (sdk_to_dict, paginate)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from mcp_server_ecs_common.convert import sdk_to_dict
from mcp_server_ecs_common.paginate import paginate


class Holder:
    """SDK-like object exposing a __dict__ (models use private attr names)."""

    def __init__(self) -> None:
        self._created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        self._size = Decimal("4096")
        self._tags = ["a"]


def test_sdk_to_dict_passthrough_scalars() -> None:
    assert sdk_to_dict(None) is None
    assert sdk_to_dict("x") == "x"
    assert sdk_to_dict(5) == 5
    assert sdk_to_dict(True) is True
    assert sdk_to_dict({"a": [1, 2]}) == {"a": [1, 2]}


def test_sdk_to_dict_recursive_containers() -> None:
    assert sdk_to_dict({"a": [{"b": 1}, 2]}) == {"a": [{"b": 1}, 2]}
    assert sdk_to_dict([{"x": "y"}, ["z"]]) == [{"x": "y"}, ["z"]]


def test_sdk_to_dict_bytes_decodes() -> None:
    assert sdk_to_dict(b"hello") == "hello"


def test_sdk_to_dict_object_with_dict_stringifies_leaves() -> None:
    assert sdk_to_dict(Holder()) == {
        "created": "2026-01-02 03:04:05+00:00",
        "size": "4096",
        "tags": ["a"],
    }


def test_sdk_to_dict_uses_to_dict_when_present() -> None:
    class WithToDict:
        def to_dict(self) -> dict[str, Any]:
            return {"name": "web", "inner": {"value": "v"}}

    assert sdk_to_dict(WithToDict()) == {"name": "web", "inner": {"value": "v"}}


def test_paginate_collects_all_pages() -> None:
    pages = [[{"id": "s-1"}, {"id": "s-2"}], [{"id": "s-3"}, {"id": "s-4"}], [{"id": "s-5"}], []]
    calls: list[int] = []
    offset = {"n": 0}

    def fetch() -> dict[str, Any]:
        page = pages[offset["n"]]
        offset["n"] += 1
        calls.append(1)
        return {"servers": page}

    result = paginate(fetch, result_key="servers", page_size=2)
    assert [s["id"] for s in result] == ["s-1", "s-2", "s-3", "s-4", "s-5"]
    assert len(calls) == 3


def test_paginate_stops_on_short_page() -> None:
    pages = [[{"id": "s-1"}], [{"id": "s-2"}]]
    offset = {"n": 0}

    def fetch() -> dict[str, Any]:
        page = pages[offset["n"]]
        offset["n"] += 1
        return {"servers": page}

    result = paginate(fetch, result_key="servers", page_size=1000)
    assert [s["id"] for s in result] == ["s-1"]
    assert offset["n"] == 1


def test_paginate_respects_max_pages() -> None:
    pages = [[{"id": "x"}] for _ in range(5)]
    offset = {"n": 0}

    def fetch() -> dict[str, Any]:
        page = pages[offset["n"]]
        offset["n"] += 1
        return {"servers": page}

    result = paginate(fetch, result_key="servers", page_size=1, max_pages=3)
    assert len(result) == 3
    assert offset["n"] == 3


def test_paginate_advance_uses_batch() -> None:
    markers: list[str] = []
    pages = [[{"id": "a"}, {"id": "b"}], [{"id": "c"}], []]
    state = {"page": 0, "marker": None}

    def fetch() -> dict[str, Any]:
        page = pages[state["page"]]
        state["page"] += 1
        return {"flavors": page}

    def advance(batch: list[dict[str, Any]], _page: dict[str, Any]) -> str | None:
        # marker-style: next marker is the last item's id of the page just fetched.
        markers.append(str(batch[-1]["id"]))
        state["marker"] = markers[-1]
        return markers[-1]

    result = paginate(fetch, result_key="flavors", page_size=2, advance=advance)
    assert len(result) == 3
    # advance runs once on the full first page; the short second page stops the loop.
    assert markers == ["b"]
