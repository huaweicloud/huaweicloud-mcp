# AGENTS.md

> Entry guide for AI agents (Cursor / Claude Code / Codex / opencode) working in this repo.
> Developer docs (authoritative): [`docs/development/`](docs/development/README.md). opencode
> users also get the condensed `huaweicloud-mcp-dev` skill (see `skills/`).

## What this repo is

`huaweicloud-mcp` — a monorepo of MCP servers for Huawei Cloud services. Each service is a
standalone, PyPI-publishable package (`mcp-server-huaweicloud-<service>`) that an MCP client
(Cursor / Claude Desktop / Trae) runs to drive that service through scenario-based tools.

## Quick start for agents

Before writing any service code, read [`docs/development/README.md`](docs/development/README.md) — it is
binding, not advisory. The fastest path: copy the reference implementation (`server/mcp_server_rfs/`)
and adapt it, or start from `docs/development/template/`. Do not invent structure.

```
docs/development/                # developer docs + scaffold template (read README.md first)
libs/huaweicloud_mcp_core/       # shared core (config/credentials/errors/security/guardrails/output/server)
server/mcp_server_<service>/     # one package per Huawei Cloud service — THREE LAYERS inside
  src/mcp_server_<service>/{tools,service,client}/
  tests/
```

## Core constraints (the short list)

- **Python >=3.10, mcp 2.x (`MCPServer`), huaweicloudsdk-*, uv, ruff, mypy strict, pytest >=80%.** See [docs/09](docs/development/09-engineering-release.md).
- **Three layers, unidirectional:** `tools -> service -> client`. No cross-layer imports. See [docs/01 §1.5](docs/development/01-architecture.md) and [docs/04](docs/development/04-service-client.md).
- **Scenario-based tools,** not 1-API-per-tool. 5–15 tools per service. See [docs/03](docs/development/03-tools.md).
- **Every tool declares `@guard(risk=ToolRisk.READ|WRITE|DANGEROUS)`**; DANGEROUS tools take `confirm: bool = False` and return a preview when false. See [docs/03 §3.8/3.9](docs/development/03-tools.md) and [docs/05](docs/development/05-guardrails.md).
- **Guardrails are auto-installed by `build_server()`** — do not bypass. Protection rules, output masking, and audit are always on. See [docs/05](docs/development/05-guardrails.md) and [docs/02 §2.9](docs/development/02-core.md).
- **Naming triplet must agree:** dist `mcp-server-huaweicloud-<svc>` / import `mcp_server_<svc>` / script `mcp-server-huaweicloud-<svc>`. Because dist != import, pyproject MUST set `[tool.hatch.build.targets.wheel] packages`. See [docs/01 §1.6](docs/development/01-architecture.md).
- **Auth from env vars only.** `HUAWEICLOUD_ACCESS_KEY/SECRET_KEY/REGION` required; `HUAWEICLOUD_PROJECT_ID` auto-resolved via IAM. No config files, no prompts. See [docs/02 §2.3/2.4](docs/development/02-core.md).
- **Structured JSON output + token budget** (default 20 items, cap 100, field whitelist). Errors use the unified envelope `{"error": {code, message, request_id, hint}}`. See [docs/06](docs/development/06-output-errors.md).

## Development flow (see [docs/08](docs/development/08-new-service-walkthrough.md) for the full walkthrough)

1. **Propose** — issue with service name + 5–15 scenario list + risk distribution.
2. **Scaffold** — `cp -r docs/development/template server/mcp_server_<svc>`, replace the naming triplet.
3. **Build bottom-up** — `client/` (against API docs) -> `service/` (orchestration + whitelist) -> `tools/` (@guard + English docstring).
4. **Self-test** — `uv sync && uv run pytest --cov` (>=80%); drive each tool via MCP Inspector / Cursor.
5. **Docs** — bilingual `README.md` + `README_zh.md` (fixed template, [docs/09 §9.4](docs/development/09-engineering-release.md)); update the repo README service table.
6. **PR** — fill the [PR checklist](docs/development/09-engineering-release.md#95-ci-与-pr-流程github-actions), local verification green, two reviewers (one core maintainer). Note: `.github/workflows/ci.yml` does not exist yet — see Known gaps.

## Reference points

| What | Where |
|---|---|
| Developer docs (authoritative) | [`docs/development/README.md`](docs/development/README.md) |
| Reference service (RFS, with full tests) | [`server/mcp_server_rfs/`](server/mcp_server_rfs/) |
| Core package | [`libs/huaweicloud_mcp_core/`](libs/huaweicloud_mcp_core/) |
| Scaffold template | [`docs/development/template/`](docs/development/template/) |
| opencode skill (condensed reference) | [`skills/huaweicloud-mcp-dev/SKILL.md`](skills/huaweicloud-mcp-dev/SKILL.md) |

## Known gaps (do not rely on — not yet implemented)

- `.github/workflows/` — CI (`ci.yml`) and release (`release.yml`) do not exist yet. Local `uv run` verification is the only check. See [docs/development/09-engineering-release.md §9.8](docs/development/09-engineering-release.md#98-当前仓库工程化状态坦白).

## Verification

```bash
cd server/mcp_server_<svc>
uv sync
uv run ruff check && uv run ruff format --check
uv run mypy src tests
uv run pytest --cov
uv run mcp-server-huaweicloud-<svc>            # stdio smoke
uv run mcp-server-huaweicloud-<svc> -t streamable-http
```
