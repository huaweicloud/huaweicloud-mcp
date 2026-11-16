# ECS Lifecycle MCP Server

> **Language:** English | [中文](./README.md)

## Version

0.1.0

## Overview

MCP Server for Huawei Cloud ECS (Elastic Cloud Server) lifecycle operations. It
lets MCP clients create, modify, and delete cloud servers through scenario
tools, with job tracking for async operations. Every changing tool follows a
strict two-call confirm protocol: the first call returns a preview of exactly
what will happen, and the operation only executes after an explicit
`confirm=true` — the agent never acts on its own.

Creation is intent-driven: pick an image / flavor / keypair with the discovery
tools (or skip them — network, disk type, and security group fall back to smart
defaults), and the preview shows the fully resolved configuration before
anything is ordered.

## Category

Compute / Elastic Cloud Server

## Features

- Create prepaid (monthly/yearly billed) servers, with order handling
- Create on-demand (pay-per-use) servers, billed per second while running
- Delete servers in batch, with explicit control over data disks and EIPs
- Update a server's name / description / hostname
- Inspect one server's full details, or list servers with filters
- Track async create/delete progress through the job status API
- Discover public images (by name keyword / OS), flavors (by vCPU / RAM), and
  SSH keypairs — the building blocks for intent-driven creation ("a cheap test
  box running Redis")
- Smart defaults on creation: omit `vpc_id` / `subnet_id` / `root_volume_type`
  and the server picks sensible values; the preview lists every fallback under
  `defaults_applied`
- Slots for the common extras: `user_data` (startup script, auto-base64),
  `security_group_id`, and `eip_bandwidth` (auto-assign an EIP, billed by
  traffic)
- Confirm protocol on all changing tools: preview first, execute only with `confirm=true`
- Second defense line: protection rules (env or `guardrails.yaml`) re-check real
  cloud attributes (id/name/tags) before any update or delete executes

## Available Tools

| Tool | Scenario | Risk | API Docs |
|---|---|---|---|
| `list_servers` | Inventory servers, filter by name / status | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `show_server` | Full details of one server | READ | [ShowServer](https://support.huaweicloud.com/api-ecs/ecs_02_0104.html) |
| `show_job` | Track an async create/delete job | READ | [ShowJob](https://support.huaweicloud.com/api-ecs/ecs_02_0901.html) |
| `list_images` | Browse images by name keyword / OS type | READ | [ListImages](https://support.huaweicloud.com/api-ims/ims_03_0602.html) |
| `list_flavors` | Browse flavors by vCPU / RAM (GB), or look up one flavor by id | READ | [ListFlavors](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0020212656.html) |
| `list_keypairs` | List existing SSH keypairs | READ | [NovaListKeypairs](https://support.huaweicloud.com/api-ecs/ecs_03_1201.html) |
| `create_server` | Create prepaid (monthly/yearly) servers | WRITE | [CreateServers](https://support.huaweicloud.com/api-ecs/ecs_02_0101.html) |
| `create_on_demand_server` | Create on-demand (pay-per-use) servers | WRITE | [CreatePostPaidServers](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0020212668.html) |
| `update_server` | Change name / description / hostname | WRITE | [UpdateServer](https://support.huaweicloud.com/api-ecs/ecs_02_0106.html) |
| `delete_servers` | Delete one or more servers | DANGEROUS | [DeleteServers](https://support.huaweicloud.com/api-ecs/ecs_02_0103.html) |

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
| `HUAWEICLOUD_ENDPOINT` | No | Override the ECS endpoint; IMS/VPC endpoints are derived from it (the `ecs.` host label is swapped for `ims.`/`vpc.`, gateway hosts are shared, and regions missing from the SDK map are synthesized as `https://ecs.<region>.myhuaweicloud.com`) | auto |
| `HUAWEICLOUD_SECURITY_TOKEN` | No | STS temporary credential token | - |
| `HUAWEICLOUD_MCP_READ_ONLY` | No | `true` blocks all WRITE/DANGEROUS tools | `false` |
| `HUAWEICLOUD_MCP_PROTECTED_IDS` | No | Guardrail: protected resource IDs (CSV, block) | empty |
| `HUAWEICLOUD_MCP_PROTECTED_NAMES` | No | Guardrail: protected resource names (CSV, block) | empty |
| `HUAWEICLOUD_MCP_PROTECTED_TAGS` | No | Guardrail: protected tags (CSV `k` or `k=v`, block) | empty |
| `HUAWEICLOUD_MCP_GUARDRAILS_CONFIG` | No | Path to `guardrails.yaml` for complex rules | empty |
| `HUAWEICLOUD_MCP_AUDIT_FILE` | No | JSONL audit file path (audit always on, stderr) | empty |
| `MCP_SERVER_PORT` | No | streamable-http port | `8000` |
| `MCP_SERVER_HOST` | No | streamable-http bind address | `0.0.0.0` |

**Confirm protocol (changing tools):** `create_server`,
`create_on_demand_server`, `update_server`, and `delete_servers` are all
two-call tools. With `confirm=false` (default) they return a preview and make
no change; with `confirm=true` they execute. Before executing, every target
server is re-checked against the protection rules (HUAWEICLOUD_MCP_PROTECTED_*
or guardrails.yaml) using its real cloud attributes — protected resources are
blocked with `MCP_GUARDRAIL_BLOCKED`.

**Safe defaults on deletion:** `delete_servers` keeps data disks (detached) and
keeps the EIP (unbound) unless `delete_volume=true` / `delete_publicip=true` is
explicitly passed and confirmed. Deleted servers cannot be recovered.

**Smart defaults on creation:** `vpc_id` / `subnet_id` / `root_volume_type` are
optional. When omitted, the server resolves them at request time: the first
subnet (alphabetically by name) supplies both subnet and VPC, and the root
volume defaults to `SSD`. The preview lists every fallback under
`defaults_applied` and shows the resolved subnet's name and CIDR, so you
confirm against the real values. If the region has no subnets (or the given
`subnet_id` is unknown), creation fails with `MCP_NOT_FOUND` — pass explicit
IDs then. Without `security_group_id` the API attaches the project default
security group; without `eip_bandwidth` no public IP is assigned.

### Running

#### Method 1: Run from source files (recommended)

First, download the source code:

```bash
git clone https://github.com/huaweicloud/huaweicloud-mcp.git
```

Using Opencode as an example:

```json
{
    "mcpServers": {
        "huaweicloud-ecs-lifecycle": {
            "type": "local",
            "args": [
                "uv",
                "--directory",
                "{directory where the code is located}/huaweicloud-mcp/server/mcp_server_ecs_lifecycle",
                "run",
                "mcp-server-ecs-lifecycle"
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

#### Method 2: Git repository uvx

```json
{
    "mcpServers": {
        "huaweicloud-ecs-lifecycle": {
            "command": "uvx",
            "type": "local",
            "args": [
                "uvx",
                "--from",
                "git+https://github.com/huaweicloud/huaweicloud-mcp#subdirectory=server/mcp_server_ecs_lifecycle",
                "mcp-server-ecs-lifecycle"
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

#### Method 3: Run as a Streamable-HTTP service

Clone the code locally, then start the service:
```bash
git clone https://github.com/huaweicloud/huaweicloud-mcp.git
cd huaweicloud-mcp/server/mcp_server_ecs_lifecycle
uv sync
uv run mcp-server-ecs-lifecycle -t streamable-http  # default port 8000
```

Configure it in the Agent using the streamable-http method.
Configuration methods may vary between Agents; please refer to the Agent documentation for details.

## Examples

### Cursor / Claude Desktop / Trae

Add the JSON snippet above to your MCP client configuration, fill in the
credentials, then ask naturally:

- "帮我开一台跑 Redis 的测试机，最便宜就行" → `list_flavors` + `list_images` + `create_on_demand_server`（AI 推导规格 / 镜像，网络与磁盘走智能默认，先预览，确认才创建）
- "列一下名字带 web 的运行中的机器" → `list_servers`
- "看看 srv-1 这台机器的详情" → `show_server`
- "有哪些 Ubuntu 22.04 镜像？" → `list_images`
- "列一下我已有的 SSH 密钥" → `list_keypairs`
- "帮我创建 2 台包周期的 web 服务器" → `create_server`（先返回预览，确认后才下单）
- "创建一台按需的测试机，用完就删" → `create_on_demand_server`（先预览，确认后才创建）
- "把 srv-1 改名为 web-prod-01" → `update_server`（先预览改前→改后，确认后才修改）
- "删掉那两台测试机" → `delete_servers`（先列出真实待删机器，确认后才删除）
- "创建任务完成了吗？" → `show_job`

## License

MIT
