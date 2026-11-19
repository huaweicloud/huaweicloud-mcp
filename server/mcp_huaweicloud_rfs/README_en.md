# RFS MCP Server

> **Language:** English | [中文](./README.md)

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

### Running

#### Option 1: Run over stdio (recommended for local use)

The Agent launches the local process itself — no manual service startup required.
Using OpenCode as an example:

```json
{
  "mcpServers": {
    "huaweicloud-rfs": {
      "type": "local",
      "command": [
        "uvx",
        "mcp-huaweicloud-rfs@latest"
      ],
      "environment": {
        "HUAWEICLOUD_ACCESS_KEY": "",
        "HUAWEICLOUD_SECRET_KEY": "",
        "HUAWEICLOUD_REGION": "cn-north-4"
      }
    }
  }
}
```

Replace `HUAWEICLOUD_ACCESS_KEY` and `HUAWEICLOUD_SECRET_KEY` with your actual values.
For production, pin a specific version instead of `@latest`.

#### Option 2: Run as a Streamable HTTP service

Suitable for remote deployment or when multiple clients share a single service.

1. Clone the code and start the service

```bash
git clone https://github.com/huaweicloud/huaweicloud-mcp.git
cd huaweicloud-mcp/server/mcp_huaweicloud_rfs
uv sync
uv run mcp-huaweicloud-rfs -t streamable-http   # listens on port 8000 by default
```

Once started, the MCP endpoint is available at http://127.0.0.1:8000/mcp.

2. Configure the MCP server in your Agent

Using OpenCode as an example:

```json
{
  "mcpServers": {
    "huaweicloud-rfs": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp",
      "env": [
        "HUAWEICLOUD_ACCESS_KEY=xxxxx",
        "HUAWEICLOUD_SECRET_KEY=xxxxx",
        "HUAWEICLOUD_REGION=xxxxx"
      ]
    }
  }
}
```

3. Verify

Restart the Agent and confirm that the MCP server shows as connected and that the RFS tools can be invoked successfully.

Notes
- Configuration field names vary between Agents (e.g. mcpServers vs. mcp, environment vs. env).
  Refer to the documentation of your specific Agent.
- Pass AK/SK through environment variables rather than hard-coding them
  in configuration files that may be committed to a repository.
- Choosing a mode: use stdio for local development and debugging;
  use Streamable HTTP for remote access or multi-client sharing.

## Examples

### Cursor / Claude Desktop / Trae

Add the JSON snippet above to your MCP client configuration, fill in the
credentials, then ask naturally:

- "Deploy this HCL template as a stack named web-app" → `deploy_stack`
- "The web-app stack deployment failed, help me diagnose the cause" → `diagnose_stack`
- "Preview what resources will be affected by the template changes" → `preview_stack_changes`
- "Delete the web-app stack" → `delete_stack` (returns preview first, executes after confirmation)

## License

MIT
