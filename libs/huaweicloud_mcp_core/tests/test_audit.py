# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the JSONL audit logger."""

from __future__ import annotations

import json

from huaweicloud_mcp_core.guardrails.audit import AuditLogger


def test_emit_writes_jsonl_to_stderr(capsys: object) -> None:
    logger = AuditLogger()
    logger.emit(tool="list_stacks", risk="READ", decision="allowed", params={"a": 1})
    captured = capsys.readouterr()
    line = captured.err.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["event"] == "tool_call"
    assert record["tool"] == "list_stacks"
    assert record["risk"] == "READ"
    assert record["decision"] == "allowed"
    assert record["params"] == {"a": 1}
    assert "ts" in record


def test_emit_appends_to_file(tmp_path: object) -> None:
    target = tmp_path / "audit.jsonl"
    logger = AuditLogger(file_path=str(target))
    logger.emit(tool="t1", decision="allowed")
    logger.emit(tool="t2", decision="blocked")
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["tool"] == "t1"
    assert json.loads(lines[1])["tool"] == "t2"


def test_emit_masks_and_trims_params(tmp_path: object) -> None:
    target = tmp_path / "audit.jsonl"
    logger = AuditLogger(file_path=str(target))
    logger.emit(
        tool="deploy_stack",
        params={"admin_password": "hunter2", "template": "x" * 500},
    )
    record = json.loads(target.read_text(encoding="utf-8").strip())
    assert record["params"]["admin_password"] == "***"
    assert len(record["params"]["template"]) == 200


def test_emit_swallows_file_errors(capsys: object) -> None:
    logger = AuditLogger(file_path="Z:/no/such/dir/audit.jsonl")
    logger.emit(tool="t", decision="allowed")
    captured = capsys.readouterr()
    assert "audit_file_error" in captured.err
