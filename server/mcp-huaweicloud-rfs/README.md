# RFS MCP Server

## Version

0.1.0

## Overview

MCP Server for Huawei Cloud RFS (Resource Formation Service). It lets MCP clients
manage infrastructure-as-code through scenario tools: deploy HCL templates as
stacks, dry-run changes with execution plans, diagnose failed deployments, and
tear stacks down safely.

## Category

Management & Governance / Infrastructure as Code

## Features

- Deploy HCL templates (inline text or OBS URL) as RFS stacks — create or update
- Dry-run template changes via execution plans (add / remove / replace diff)
- Diagnose failed or stuck stacks: aggregated status, failed events, failed
  resources, root-cause conclusions
- Inventory stacks with pagination
- Read stack metadata and outputs
- Delete stacks with an explicit confirmation flow and resource preview

## Available Tools

| Tool | Scenario | Risk | API Docs |
|---|---|---|---|
| `list_stacks` | Inventory stacks, filter by name | READ | [ListStacks](https://support.huaweicloud.com/api-rfs/rfs_02_0031.html) |
| `get_stack` | Stack metadata + outputs | READ | [GetStackMetadata](https://support.huaweicloud.com/api-rfs/rfs_02_0033.html) / [ListStackOutputs](https://support.huaweicloud.com/api-rfs/rfs_02_0041.html) |
| `preview_stack_changes` | Dry-run diff before deploying | READ | [CreateExecutionPlan](https://support.huaweicloud.com/api-rfs/rfs_02_0051.html) / [GetExecutionPlan](https://support.huaweicloud.com/api-rfs/rfs_02_0053.html) |
| `deploy_stack` | Create or update a stack from a template | WRITE | [CreateStack](https://support.huaweicloud.com/api-rfs/rfs_02_0021.html) / [DeployStack](https://support.huaweicloud.com/api-rfs/rfs_02_0027.html) |
| `diagnose_stack` | Root-cause failed deployments | READ | [ListStackEvents](https://support.huaweicloud.com/api-rfs/rfs_02_0037.html) / [ListStackResources](https://support.huaweicloud.com/api-rfs/rfs_02_0039.html) |
| `delete_stack` | Tear down a stack (confirmation required) | DANGEROUS | [DeleteStack](https://support.huaweicloud.com/api-rfs/rfs_02_0029.html) |

## Usage Guide

### Prerequisites

- Python 3.10+
- UV

**Linux/macOS:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Installation

```bash
git clone <repo-url>
cd huaweicloud-mcp/server/mcp-huaweicloud-rfs
uv sync
uv run mcp-huaweicloud-rfs          # stdio (default)
uv run mcp-huaweicloud-rfs -t streamable-http
```

## Configuration

### Environment Variables

| Variable | Required | Description | Default |
|---|---|---|---|
| `HUAWEICLOUD_ACCESS_KEY` | Yes | Account access key | - |
| `HUAWEICLOUD_SECRET_KEY` | Yes | Account secret key | - |
| `HUAWEICLOUD_REGION` | Yes | Resource region (e.g. `cn-north-4`) | - |
| `HUAWEICLOUD_PROJECT_ID` | No | Override project_id (auto-resolved via IAM by default) | auto |
| `HUAWEICLOUD_SECURITY_TOKEN` | No | STS temporary credential token | - |
| `HUAWEICLOUD_MCP_READ_ONLY` | No | `true` blocks all WRITE/DANGEROUS tools | `false` |
| `HUAWEICLOUD_MCP_PROTECTED_IDS` | No | Guardrail: protected resource IDs (CSV, block) | empty |
| `HUAWEICLOUD_MCP_PROTECTED_NAMES` | No | Guardrail: protected resource names (CSV, block) | empty |
| `HUAWEICLOUD_MCP_PROTECTED_TAGS` | No | Guardrail: protected tags (CSV `k` or `k=v`, block) | empty |
| `HUAWEICLOUD_MCP_GUARDRAILS_CONFIG` | No | Path to `guardrails.yaml` for complex rules | empty |
| `HUAWEICLOUD_MCP_AUDIT_FILE` | No | JSONL audit file path (audit always on, stderr) | empty |
| `MCP_SERVER_PORT` | No | streamable-http port | `8000` |
| `MCP_SERVER_HOST` | No | streamable-http bind address | `0.0.0.0` |

**Guardrail limitation (parameter-level matching):** protection rules match
resource IDs / name-like parameters / explicitly passed tags in tool arguments.
A resource that only carries a protection tag on the cloud side (not present in
the arguments) is matched by the second defense line: `delete_stack` re-checks
the stack's real attributes before the irreversible call.

### Run with uvx

From the git repository:

```json
{
    "mcpServers": {
        "huaweicloud-rfs": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/<org>/huaweicloud-mcp#subdirectory=server/mcp-huaweicloud-rfs",
                "mcp-huaweicloud-rfs"
            ],
            "env": {
                "HUAWEICLOUD_ACCESS_KEY": "",
                "HUAWEICLOUD_SECRET_KEY": "",
                "HUAWEICLOUD_REGION": ""
            }
        }
    }
}
```

## Examples

### Cursor / Claude Desktop / Trae

Add the JSON snippet above to your MCP client configuration, fill in the
credentials, then ask naturally:

- "帮我把这个 HCL 模板部署成名为 web-app 的资源栈" → `deploy_stack`
- "web-app 栈部署失败了，帮我看看原因" → `diagnose_stack`
- "预览一下模板改动会影响哪些资源" → `preview_stack_changes`
- "删掉 web-app 这个栈" → `delete_stack`（先返回预览，确认后执行）

## License

MIT
