# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""JSON-compatible conversion of huaweicloudsdk response objects.

The SDK deserializer yields model instances and nested containers; these
helpers turn an arbitrary response into plain JSON data so the MCP layer can
serialize it without leaking SDK internals.
"""

from __future__ import annotations

from typing import Any

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
        # datetime/Decimal/etc. have no __dict__ — the SDK deserializer can emit
        # them for time-typed fields even when models declare plain str.
        result = str(obj)
    else:
        result = {}
        for key, value in vars(obj).items():
            if key in _SKIP_ATTRS or key.startswith("__") or callable(value):
                continue
            result[key.lstrip("_")] = sdk_to_dict(value)
    return result
