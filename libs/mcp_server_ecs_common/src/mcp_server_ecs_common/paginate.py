# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Generic page-through helper for huaweicloudsdk list endpoints.

Each SDK list call that can return more than one page shares the same
shape: build a request with a page size, fetch one page, collect the
items, and keep going until the page comes back short or empty. This
module factors that loop into one place; the per-endpoint request
construction and pagination-state advancement stay in the caller.

Two paging styles are supported:

* offset style (ECS list-servers-details): the caller advances an integer
  offset and the loop stops when a page is empty or short.
* marker style (IMS list-images, ECS list-flavors, VPC list-subnets): the
  caller reads ``page_info.next_marker`` from the response. When ``advance``
  returns the next marker (a string), the loop follows it; an empty/None
  marker means the last page. This is authoritative — a full last page does
  not cause an extra fetch, and a repeated marker is detected to avoid
  looping forever on a misbehaving endpoint.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp_server_ecs_common.convert import sdk_to_dict


def paginate(
    fetch: Callable[[], Any],
    *,
    result_key: str,
    page_size: int,
    max_pages: int | None = None,
    advance: Callable[[list[dict[str, Any]], dict[str, Any]], str | None] | None = None,
) -> list[dict[str, Any]]:
    """Collect every item a paged list endpoint returns.

    ``fetch`` builds the SDK request (already carrying the current page
    position) and returns the raw response object for one page. ``advance``,
    when given, receives the batch just received plus the decoded page dict
    and returns the next marker (or ``None`` when there are no more pages).
    Iteration stops when a page is empty, comes back short of ``page_size``
    (offset style), the marker is exhausted (marker style), the marker
    repeats, or ``max_pages`` is exhausted. Without ``advance`` a full page
    keeps the loop going; pass ``max_pages`` to bound it.

    Runs synchronously; callers wrap it in ``call_sdk`` (which in turn wraps
    ``asyncio.to_thread`` with concurrency limiting and retry) exactly as they
    do for their single-page calls.
    """
    items: list[dict[str, Any]] = []
    pages = 0
    seen_markers: set[str] = set()
    while max_pages is None or pages < max_pages:
        pages += 1
        response = fetch()
        page = sdk_to_dict(response) or {}
        batch = page.get(result_key) or []
        items.extend(batch)
        if not batch or len(batch) < page_size:
            break
        if advance is None:
            continue
        next_marker = advance(batch, page)
        if next_marker is None:
            break
        if next_marker in seen_markers:
            # A marker that repeats means the endpoint is not advancing; stop
            # rather than spin until max_pages on duplicate data.
            break
        seen_markers.add(next_marker)
    return items
