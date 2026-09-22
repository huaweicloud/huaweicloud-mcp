---
name: huaweicloud-mcp-dev
description: 'Use when developing Huawei Cloud MCP servers/tools in this repo: creating a new mcp_server_* service, adding or modifying MCP tools, wiring the three-layer architecture, declaring tool risk/guardrails, or onboarding a new Huawei Cloud service. Triggers: mcp_server_, MCP tool, MCP server, 新建服务, 添加工具, 接入新服务, 三层架构, 场景化工具, 护栏, guard, ToolRisk, assert_not_protected, build_server, huaweicloud-mcp. NOT for: running hcloud CLI operations on existing cloud resources (use huawei-ecs / huawei-obs / huawei-vpc etc.), or non-MCP application code.'
version: 1
---

# Huawei Cloud MCP Server Development

**STOP — do not answer from general knowledge.** This repo has a binding spec.
Authoritative detail lives in `docs/development/` (repo root); this skill is the
fast-action condensation. When a decision needs depth, read the cited section.

The reference implementation is `server/mcp_server_rfs/` (RFS, full tests) — copy
its shape, do not invent.

## Tech stack (non-negotiable)

| Item | Value |
|---|---|
| Python | >=3.10 |
| MCP SDK | mcp 2.x — `MCPServer` (FastMCP renamed; see spec §16 B.8) |
| Cloud SDK | `huaweicloudsdk-core` + `huaweicloudsdk-<service>` |
| Pkg mgr | uv |
| Lint/type/test | ruff + mypy strict + pytest (coverage >=80%) |

## Repo layout

```
libs/huaweicloud_mcp_core/   # shared core: config/credentials/errors/security/guardrails/output/server
server/mcp_server_<svc>/     # one package per Huawei Cloud service
  src/mcp_server_<svc>/{tools,service,client}/   # THREE LAYERS (mandatory)
  tests/
docs/development/template/    # scaffold (see onboarding, §13)
```

Naming triplet must agree: dist `mcp-server-huaweicloud-<svc>` / import `mcp_server_<svc>` /
script `mcp-server-huaweicloud-<svc>`. dist != import, so pyproject MUST declare
`[tool.hatch.build.targets.wheel] packages = ["src/mcp_server_<svc>"]` (spec §5.1, §16 B.8).

## The three layers (mandatory, unidirectional tools -> service -> client)

| Layer | Dir | Does | Must NOT |
|---|---|---|---|
| tools | `tools/` | `@server.tool()` + `@guard(risk=...)`; English docstring; calls service; thin | import `huaweicloudsdk*`; business logic |
| service | `service/` | orchestration; multi-API composition; pagination clamp; field whitelist; confirm preview; `assert_not_protected` before irreversible ops | build SDK client; know about MCP framework |
| client | `client/` | thin async wrapper (`asyncio.to_thread`) around sync SDK; 404->None; `wrap_sdk_error` | business logic; reshape responses |

See spec §4, §5 for templates; `server/mcp_server_rfs/` for a worked example.

## Scenario-based tools (spec §6) — this is NOT 1-API-per-tool

- One tool = one user intent; may orchestrate 1..n API calls.
- 5–15 tools per service in the first batch.
- Name: `verb_noun[_qualifier]`, snake_case, <=40 chars. Verb table in §6.5.
- Banned names: `handle_*` / `do_*` / `*_v2` / `execute_api`.
- Docstring: English, structure = one-line -> scenario -> Args (meaning+example+constraint) -> Returns. Give prerequisite hints ("run list_flavors first").
- Params: JSON primitives only; enums listed in description; dates ISO 8601; optional params have safe defaults.
- Long tasks: return task id + companion query tool; if waiting is needed, offer `wait` flag with timeout cap (see RFS `deploy_stack`).

## Risk levels & guardrails (spec §7) — declared by `@guard`, enforced by middleware

Every tool MUST `@guard(risk=ToolRisk.READ|WRITE|DANGEROUS)`:
- READ: no state change (list/get/analyze/diagnose)
- WRITE: recoverable/recreatable change (create/update/stop/resize)
- DANGEROUS: irreversible delete/release/data-loss (delete/release/clean) — MUST define `confirm: bool = False`; `confirm=False` returns a preview (with resource name+tags), no mutation.

`build_server()` auto-installs `GuardrailsMiddleware` (do NOT bypass). Pipeline per call:
read-only check -> risk-declaration check -> protection rules -> confirm -> execute -> mask output -> audit.

Guardrail actions: `block` (MCP_GUARDRAIL_BLOCKED) / `warn` (inject `warnings[]`) / `confirm` (escalate; degrades to `block` if the tool has no `confirm` param).

Rules come from env vars (simple) + optional `guardrails.yaml` (complex). Match is parameter-level (id exact/prefix, name-like param regex, explicit tags arg). Blind spot: a resource protected by a cloud-side tag not present in the args -> second defense line: DANGEROUS service orchestration MUST call `assert_not_protected(resource)` with the real cloud attributes before the irreversible call.

Output masking is always on (AK/SK/token/password-field/PEM/Bearer). Audit is always on (JSONL to stderr + optional file). Fail-closed: engine error blocks WRITE/DANGEROUS, allows READ.

## Output & errors (spec §8)

- Always structured JSON. Lists via `page_result` (items/count/total/marker/truncated).
- Token budget: default 20 items, hard cap 100; field whitelist; long strings truncated at 2000 chars + `_truncated: true`.
- Errors: unified envelope `{"error": {code, message, request_id, doc_url, hint}}`. hint MUST give a next step. request_id MUST pass through (for support tickets).
- Internal codes: MCP_INVALID_ARGS / MCP_NOT_FOUND / MCP_PERMISSION_DENIED / MCP_READ_ONLY / MCP_GUARDRAIL_BLOCKED / MCP_GUARDRAIL_ERROR / MCP_SDK_ERROR.
- `@guard` catches `McpToolError` and returns the envelope — never raise raw to the framework.

## Auth & config (spec §9) — env vars only

`HUAWEICLOUD_ACCESS_KEY / SECRET_KEY / REGION` required. `HUAWEICLOUD_PROJECT_ID` optional (auto-resolved via IAM, cached; needs IAM read perm). `HUAWEICLOUD_SECURITY_TOKEN` optional (STS). `HUAWEICLOUD_MCP_READ_ONLY=true` blocks writes. Guardrail env: `HUAWEICLOUD_MCP_PROTECTED_IDS/NAMES/TAGS`, `HUAWEICLOUD_MCP_GUARDRAILS_CONFIG`, `HUAWEICLOUD_MCP_AUDIT_FILE`. No config files, no interactive prompts (stdin is the MCP channel).

## mcp 2.x specifics (spec §16 B.8 — gotchas that bite)

- `from mcp.server.mcpserver import MCPServer` (NOT FastMCP; the shim raises).
- Middleware = `ServerMiddleware` protocol: `async __call__(ctx, call_next)` wraps ALL inbound requests; dispatch on `ctx.method == "tools/call"`; tool name/args from `ctx.params` (raw mapping). The core `GuardrailsMiddleware` already does this — services never touch it.
- Interception results (error envelope, confirmation_required) MUST set BOTH `content` (text JSON) AND `structured_content` (dict) — mcp 2.x clients validate against the tool's output schema.
- `MCPServer.__init__` takes NO host/port; `run(transport="streamable-http", host=..., port=...)` carries them. `run_standard()` handles this.
- types fields are snake_case: `is_error`, `structured_content` (NOT camelCase).

## Onboarding a new service (spec §13) — follow in order

1. Issue: service name, 5–15 scenario list, risk-level distribution.
2. Scaffold: `cp -r docs/development/template server/mcp_server_<svc>`, replace the naming triplet.
3. Build bottom-up: `client/` (vs API docs) -> `service/` (orchestration + whitelist) -> `tools/` (@guard + docstring).
4. Self-test: `uv run pytest` (>=80%); run the server + drive each tool via MCP Inspector / Cursor.
5. Docs: bilingual README.md + README_zh.md (fixed section template, spec §12); update repo README service table.
6. PR: fill the checklist, CI green, two reviewers (one core maintainer).

## PR checklist (condensed — full in spec §13)

- [ ] naming triplet agrees; pyproject has `[tool.hatch.build.targets.wheel] packages`
- [ ] strict three layers, no cross-layer import
- [ ] every tool has `@guard(risk=...)`; DANGEROUS has `confirm`, `confirm=False` is side-effect-free
- [ ] every tool has full English docstring (scenario/Args/Returns/prereq)
- [ ] lists via `page_result`, limit default 20 cap 100, field whitelist
- [ ] errors unified JSON, no raw exceptions
- [ ] credentials from env only; no AK/SK/token in logs/output
- [ ] read-only mode blocks WRITE/DANGEROUS (tested)
- [ ] DANGEROUS orchestration calls `assert_not_protected` before irreversible op (tested)
- [ ] confirm preview echoes resource name + tags
- [ ] block/warn/confirm rule actions each have a hit test
- [ ] guardrail not bypassed (no swallowing guardrail exceptions, build_server call chain intact)
- [ ] README declares parameter-level matching blind spot + guardrail config example
- [ ] mypy strict, coverage >=80%, CI green
- [ ] bilingual README complete, tool table links official API docs
- [ ] core package public interface unchanged (or separate migration PR)
- [ ] uv.lock committed; deps pinned (SDK `>=x.y`, core `>=1.0,<2`)

## Verification commands

```bash
cd server/mcp_server_<svc>
uv sync
uv run ruff check && uv run ruff format --check
uv run mypy
uv run pytest --cov
uv run mcp-server-huaweicloud-<svc>            # stdio; smoke with MCP Inspector / Cursor
uv run mcp-server-huaweicloud-<svc> -t streamable-http
```

## Where to look

- `docs/development/` — full spec (cited by section above); `DEVELOPMENT_SPEC2.md` is the legacy single-file backup
- `server/mcp_server_rfs/` — reference implementation (client/service/tools/tests)
- `libs/huaweicloud_mcp_core/` — core package (config/credentials/guardrails/output/server)
- `docs/development/template/` — scaffold for new services
