# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Structured JSONL audit logging (always on)."""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from huaweicloud_mcp_core.guardrails.masking import MaskingEngine

_MAX_PARAM_LENGTH = 200


def _trim_params(params: Any) -> Any:
    if isinstance(params, dict):
        return {
            str(key): _trim_params(value)
            for key, value in params.items()
            if value is not None
        }
    if isinstance(params, (list, tuple)):
        return [_trim_params(item) for item in params]
    if isinstance(params, str) and len(params) > _MAX_PARAM_LENGTH:
        return params[:_MAX_PARAM_LENGTH]
    return params


class AuditLogger:
    """Emits one JSONL record per tool call to stderr and (optionally) a file."""

    def __init__(
        self,
        file_path: str | None = None,
        masking: MaskingEngine | None = None,
    ) -> None:
        self._file_path = file_path
        self._masking = masking or MaskingEngine()

    @property
    def file_path(self) -> str | None:
        return self._file_path

    def emit(self, **event: Any) -> None:
        record: dict[str, Any] = {
            "ts": _utc_timestamp(),
            "event": "tool_call",
        }
        record.update(event)
        if "params" in record:
            record["params"] = self._masking.mask(_trim_params(record["params"]))
        line = json.dumps(record, ensure_ascii=False, default=str)
        print(line, file=sys.stderr)
        if self._file_path:
            try:
                with open(self._file_path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError:
                fallback = json.dumps({"event": "audit_file_error", "path": self._file_path})
                print(fallback, file=sys.stderr)


def _utc_timestamp() -> str:
    now = time.time()
    base = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
    return f"{base}.{int(now * 1000) % 1000:03d}Z"
