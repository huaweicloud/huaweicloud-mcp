# ECS Readonly MCP Server

> **Language:** English | [中文](./README.md)

## Version

0.1.0

## Overview

Read-only MCP Server for Huawei Cloud ECS (Elastic Cloud Server). It lets MCP clients audit
cloud server usage through scenario tools: count instances, break down power
states, inventory flavors, sum up active vCPU/memory, and review public/private
IP usage — designed for periodic fleet reviews by AI agents.

## Category

Compute / Elastic Cloud Server

## Features

- List cloud servers with optional name / status / flavor filters
- Count all servers, or group them by power state (ACTIVE / SHUTOFF / ERROR...)
- Inventory instance flavors with per-flavor server counts
- Sum active vCPU and memory (GB) across running servers
- Count public vs private IPs in use across the fleet
- Read-only: every tool declares READ risk; no destructive operations

## Available Tools

| Tool | Scenario | Risk | API Docs |
|---|---|---|---|
| `list_servers` | Inventory servers, filter by name / status / flavor | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `count_servers` | Total server count | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `count_servers_by_status` | Count servers grouped by power state | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `list_server_flavors` | Flavor inventory with per-type counts | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `analyze_server_resources` | Active vCPU / memory totals | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `analyze_server_ips` | Public / private IP usage | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |

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
| `HUAWEICLOUD_PROJECT_ID` | Yes | ID of the project hosting your resources (console: My Credentials > Project List, e.g. `0610f92e7d124d4a9e4d8e8d95b4a4d0`) | - |
| `HUAWEICLOUD_ENDPOINT` | No | Override the ECS endpoint (regions missing from the SDK map are synthesized as `https://ecs.<region>.myhuaweicloud.com` automatically) | auto |
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
This server is read-only — it exposes no delete/stop/rebuild tools — so the
protection guardrails act as an output-masking and audit layer here rather than
a write blocker.

### Running

#### Option 1: Run over stdio (recommended for local use)

The Agent launches the local process itself — no manual service startup required.
Using OpenCode as an example:

```json
{
  "mcpServers": {
    "huaweicloud-ecs-readonly": {
      "type": "local",
      "command": [
        "uvx",
        "mcp-huaweicloud-ecs-readonly@latest"
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
cd huaweicloud-mcp/server/mcp_huaweicloud_ecs_readonly
uv sync
uv run mcp-huaweicloud-ecs-readonly -t streamable-http   # listens on port 8000 by default
```

Once started, the MCP endpoint is available at http://127.0.0.1:8000/mcp.

2. Configure the MCP server in your Agent

Using OpenCode as an example:

```json
{
  "mcpServers": {
    "huaweicloud-ecs-readonly": {
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

Restart the Agent and confirm that the MCP server shows as connected and that the ECS read-only tools can be invoked successfully.

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

- "我们一共有多少台云服务器？" → `count_servers`
- "有多少机器在跑，多少关着的？" → `count_servers_by_status`
- "都用了哪些规格，每种几台？" → `list_server_flavors`
- "运行中的机器一共多少核、多少内存？" → `analyze_server_resources`
- "哪些机器挂了公网 IP？" → `analyze_server_ips`
- "列一下名字带 web 的运行中的机器" → `list_servers`

## License

MIT
