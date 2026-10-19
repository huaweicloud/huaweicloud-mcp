# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for guardrail rule loading and evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest

from huaweicloud_mcp_core.errors import McpToolError
from huaweicloud_mcp_core.guardrails.rules import (
    ResourceSpec,
    Rule,
    evaluate_rules,
    load_rules,
    strictest_hit,
)
from huaweicloud_mcp_core.security import ToolRisk


def _rule(rule_id: str, action: str, **kwargs: object) -> Rule:
    return Rule(id=rule_id, action=action, **kwargs)  # type: ignore[arg-type]


def test_env_lists_generate_block_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_IDS", "stack-1,stack-2")
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_NAMES", "prod-web")
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_TAGS", "env=prod,critical")
    rules = load_rules()
    assert [rule.id for rule in rules] == [
        "env-protected-ids",
        "env-protected-names",
        "env-protected-tags",
    ]
    assert all(rule.action == "block" for rule in rules)


def test_yaml_rules_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "guardrails.yaml"
    config.write_text(
        """
version: 1
rules:
  - id: protect-prod
    description: protect production stacks
    match:
      tools: ["delete_*"]
      risks: [DANGEROUS]
      resources:
        name_patterns: ["^prod-"]
    action: block
    message: Production stacks are protected.
  - id: staging-confirm
    match:
      resources:
        tags: ["env=staging"]
    action: confirm
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HUAWEICLOUD_MCP_GUARDRAILS_CONFIG", str(config))
    rules = load_rules()
    assert len(rules) == 2
    assert rules[0].tools == ("delete_*",)
    assert rules[0].risks == (ToolRisk.DANGEROUS,)
    assert rules[0].resources.name_patterns == ("^prod-",)
    assert rules[1].action == "confirm"


def test_invalid_action_fails_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "guardrails.yaml"
    config.write_text("rules:\n  - id: bad\n    action: explode\n", encoding="utf-8")
    monkeypatch.setenv("HUAWEICLOUD_MCP_GUARDRAILS_CONFIG", str(config))
    with pytest.raises(McpToolError, match="invalid action"):
        load_rules()


def test_duplicate_rule_id_fails_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "guardrails.yaml"
    config.write_text(
        "rules:\n  - id: dup\n    action: warn\n  - id: dup\n    action: block\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HUAWEICLOUD_MCP_GUARDRAILS_CONFIG", str(config))
    with pytest.raises(McpToolError, match="Duplicate"):
        load_rules()


def test_invalid_regex_fails_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "guardrails.yaml"
    config.write_text(
        "rules:\n"
        "  - id: bad-re\n"
        "    match:\n"
        "      resources:\n"
        '        name_patterns: ["[unclosed"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HUAWEICLOUD_MCP_GUARDRAILS_CONFIG", str(config))
    with pytest.raises(McpToolError, match="invalid name pattern"):
        load_rules()


def test_missing_config_file_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUAWEICLOUD_MCP_GUARDRAILS_CONFIG", "Z:/nope/missing.yaml")
    with pytest.raises(McpToolError, match="Cannot read"):
        load_rules()


def test_evaluate_matches_tool_glob_and_resource() -> None:
    rules = [
        _rule(
            "r1",
            "block",
            tools=("delete_*",),
            risks=(ToolRisk.DANGEROUS,),
            resources=ResourceSpec(name_patterns=("^prod-",)),
        )
    ]
    hits = evaluate_rules(rules, "delete_stack", ToolRisk.DANGEROUS, {"stack_name": "prod-web"})
    assert [hit.rule.id for hit in hits] == ["r1"]
    assert hits[0].matched_via.startswith("name:")


def test_evaluate_skips_non_matching_tool() -> None:
    rules = [
        _rule("r1", "block", tools=("delete_*",), resources=ResourceSpec(name_patterns=("^prod-",)))
    ]
    hits = evaluate_rules(rules, "deploy_stack", ToolRisk.WRITE, {"stack_name": "prod-web"})
    assert hits == []


def test_evaluate_skips_non_matching_risk() -> None:
    rules = [_rule("r1", "block", risks=(ToolRisk.DANGEROUS,), resources=ResourceSpec(ids=("x",)))]
    hits = evaluate_rules(rules, "delete_stack", ToolRisk.WRITE, {"id": "x"})
    assert hits == []


def test_evaluate_rule_without_resource_filter_matches_all() -> None:
    rules = [_rule("r1", "warn", tools=("deploy_*",))]
    hits = evaluate_rules(rules, "deploy_stack", ToolRisk.WRITE, {"stack_name": "anything"})
    assert [hit.matched_via for hit in hits] == ["no-resource-filter"]


def test_strictest_hit_prefers_block_over_warn() -> None:
    hits = evaluate_rules(
        [
            _rule("warn-rule", "warn", tools=("deploy_*",)),
            _rule("block-rule", "block", tools=("deploy_*",), resources=ResourceSpec(ids=("s-1",))),
        ],
        "deploy_stack",
        ToolRisk.WRITE,
        {"stack_name": "s-1"},
    )
    strictest = strictest_hit(hits)
    assert strictest is not None
    assert strictest.rule.id == "block-rule"


def test_strictest_hit_empty() -> None:
    assert strictest_hit([]) is None
