# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Guardrail rule model, loading and evaluation."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.errors import McpToolError
from huaweicloud_mcp_core.security import ToolRisk

VALID_ACTIONS = ("block", "confirm", "warn")
ACTION_ORDER = {"warn": 0, "confirm": 1, "block": 2}


@dataclass(frozen=True)
class ResourceSpec:
    ids: tuple[str, ...] = ()
    id_prefixes: tuple[str, ...] = ()
    name_patterns: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (self.ids or self.id_prefixes or self.name_patterns or self.tags)

    @property
    def regexes(self) -> tuple[re.Pattern[str], ...]:
        return tuple(re.compile(pattern) for pattern in self.name_patterns)


@dataclass(frozen=True)
class Rule:
    id: str
    action: str
    message: str = ""
    description: str = ""
    tools: tuple[str, ...] = ()
    risks: tuple[ToolRisk, ...] = ()
    resources: ResourceSpec = field(default_factory=ResourceSpec)

    def matches_tool(self, tool_name: str, risk: ToolRisk) -> bool:
        if self.tools and not any(
            fnmatch.fnmatchcase(tool_name, pattern) for pattern in self.tools
        ):
            return False
        return not self.risks or risk in self.risks


@dataclass(frozen=True)
class RuleHit:
    rule: Rule
    matched_via: str


def load_rules(settings: McpSettings | None = None) -> list[Rule]:
    """Merge environment-variable lists with the optional YAML config (fail-fast)."""
    settings = settings or McpSettings.from_env(require_credentials=False)
    rules: list[Rule] = []
    if settings.protected_ids:
        rules.append(
            Rule(
                id="env-protected-ids",
                action="block",
                message="Resource ID is in the protected list (HUAWEICLOUD_MCP_PROTECTED_IDS).",
                resources=ResourceSpec(ids=settings.protected_ids),
            )
        )
    if settings.protected_names:
        rules.append(
            Rule(
                id="env-protected-names",
                action="block",
                message="Resource name is in the protected list (HUAWEICLOUD_MCP_PROTECTED_NAMES).",
                resources=ResourceSpec(
                    name_patterns=tuple(f"^{re.escape(name)}$" for name in settings.protected_names)
                ),
            )
        )
    if settings.protected_tags:
        rules.append(
            Rule(
                id="env-protected-tags",
                action="block",
                message="Resource tag is in the protected list (HUAWEICLOUD_MCP_PROTECTED_TAGS).",
                resources=ResourceSpec(tags=settings.protected_tags),
            )
        )
    if settings.guardrails_config_path:
        rules.extend(_load_yaml_rules(settings.guardrails_config_path))
    _validate(rules)
    return rules


def _load_yaml_rules(path: str) -> list[Rule]:
    try:
        with open(path, encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise McpToolError(
            code="MCP_GUARDRAIL_ERROR",
            message=f"Cannot read guardrails config '{path}': {exc}",
            hint="Fix the file path or unset HUAWEICLOUD_MCP_GUARDRAILS_CONFIG.",
        ) from exc
    except yaml.YAMLError as exc:
        raise McpToolError(
            code="MCP_GUARDRAIL_ERROR",
            message=f"Invalid YAML in guardrails config '{path}': {exc}",
            hint="Fix the YAML syntax; see the spec section 7.3 for the schema.",
        ) from exc
    if not isinstance(payload, dict):
        raise McpToolError(
            code="MCP_GUARDRAIL_ERROR",
            message=f"Guardrails config '{path}' must be a YAML mapping.",
            hint="See the spec section 7.3 for the schema.",
        )
    rules: list[Rule] = []
    for raw in payload.get("rules") or []:
        match = raw.get("match") or {}
        resources_raw = match.get("resources") or {}
        resources = ResourceSpec(
            ids=tuple(resources_raw.get("ids") or ()),
            id_prefixes=tuple(resources_raw.get("id_prefixes") or ()),
            name_patterns=tuple(resources_raw.get("name_patterns") or ()),
            tags=tuple(resources_raw.get("tags") or ()),
        )
        risks = tuple(ToolRisk(value) for value in match.get("risks") or [])
        rules.append(
            Rule(
                id=str(raw["id"]),
                action=str(raw.get("action", "block")),
                message=str(raw.get("message", "")),
                description=str(raw.get("description", "")),
                tools=tuple(match.get("tools") or ()),
                risks=risks,
                resources=resources,
            )
        )
    return rules


def _validate(rules: list[Rule]) -> None:
    seen: set[str] = set()
    for rule in rules:
        if rule.action not in VALID_ACTIONS:
            raise McpToolError(
                code="MCP_GUARDRAIL_ERROR",
                message=f"Rule '{rule.id}' has invalid action '{rule.action}'.",
                hint=f"Allowed actions: {', '.join(VALID_ACTIONS)}.",
            )
        if rule.id in seen:
            raise McpToolError(
                code="MCP_GUARDRAIL_ERROR",
                message=f"Duplicate guardrail rule id '{rule.id}'.",
                hint="Rule ids must be globally unique.",
            )
        seen.add(rule.id)
    for rule in rules:
        for pattern in rule.resources.name_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise McpToolError(
                    code="MCP_GUARDRAIL_ERROR",
                    message=f"Rule '{rule.id}' has invalid name pattern '{pattern}': {exc}",
                    hint="Fix the regular expression in the guardrails config.",
                ) from exc


def evaluate_rules(
    rules: list[Rule],
    tool_name: str,
    risk: ToolRisk,
    arguments: dict[str, Any],
) -> list[RuleHit]:
    """Evaluate all rules; return every hit (strictest action wins upstream)."""
    from huaweicloud_mcp_core.guardrails.protect import match_arguments

    hits: list[RuleHit] = []
    for rule in rules:
        if not rule.matches_tool(tool_name, risk):
            continue
        if rule.resources.is_empty():
            hits.append(RuleHit(rule=rule, matched_via="no-resource-filter"))
            continue
        via = match_arguments(rule.resources, arguments)
        if via:
            hits.append(RuleHit(rule=rule, matched_via=via))
    return hits


def strictest_hit(hits: list[RuleHit]) -> RuleHit | None:
    if not hits:
        return None
    return max(hits, key=lambda hit: ACTION_ORDER[hit.rule.action])
