# RC MCP Server

## Version

0.1.0

## Overview

MCP Server for Huawei Cloud RC (Resource Center), providing global resource
management. Users can search their cloud resources, view resource details and
the relationships between resources, and organize resources into groups. It
also supports custom advanced queries to check the configuration state of
resources under specified conditions via ResourceQL.

## Category

Management & Governance / Resource Center

## Features

**Resource Query**

- List all resources with filters (resource name, resource ID, tags,
  enterprise project, region, resource type)
- Show a single resource's detail by resource ID
- List the cloud services, resources, and regions supported by RC

**Resource Relationships**

- Show the relations between a resource and other resources by resource ID

**Resource Groups**

- Create, update, delete, show, and list resource groups
- Add resources to a group in batch and remove a resource from a group

**Advanced Queries**

- Run ResourceQL advanced queries
- Create, list, show, update, and delete advanced queries

**General**

- Structured JSON output with pagination and field whitelisting
- AK/SK authentication via environment variables (shared core package)
- Security guardrails auto-installed (risk declaration, output masking, audit)

## Available Tools

| Tool | Scenario | Risk | API |
|---|---|---|---|
| `list_providers` | List all cloud service providers | READ | `GET /v1/resource-center/all-providers` |
| `list_all_resources` | List all resources with filters | READ | `GET /v1/resource-center/all-resources` |
| `show_resource_detail` | Show a single resource by ID | READ | `GET /v1/resource-center/all-resources/{resource_id}` |
| `list_all_tags` | List all resource tags | READ | `GET /v1/resource-center/all-resources/tags` |
| `count_all_resources` | Count resources by filters | READ | `GET /v1/resource-center/all-resources/count` |
| `collect_resources_summary` | Per-provider/type/region summary | READ | `GET /v1/resource-center/all-resources/summary` |
| `create_resource_group` | Create a resource group | WRITE | `POST /v1/resource-center/groups` |
| `update_resource_group` | Update a resource group description | WRITE | `PATCH /v1/resource-center/groups/{group_id}` |
| `delete_resource_group` | Delete a resource group (confirm) | DANGEROUS | `DELETE /v1/resource-center/groups/{group_id}` |
| `show_resource_group` | Show a resource group | READ | `GET /v1/resource-center/groups/{group_id}` |
| `list_resource_groups` | List resource groups | READ | `GET /v1/resource-center/groups` |
| `add_resources_to_group` | Add resources to a group | WRITE | `PUT /v1/resource-center/groups/{group_id}/resources` |
| `remove_resource_from_group` | Remove a resource from a group | WRITE | `DELETE /v1/resource-center/groups/{group_id}/resources/{resource_id}` |
| `show_resource_relations` | Show a resource's relations | READ | `GET /v1/resource-center/resource-relations` |
| `run_query` | Execute an advanced query | READ | `POST /v1/resource-center/run-query` |
| `create_stored_query` | Create an advanced query | WRITE | `POST /v1/resource-center/stored-queries` |
| `list_stored_queries` | List advanced queries | READ | `GET /v1/resource-center/stored-queries` |
| `show_stored_query` | Show an advanced query | READ | `GET /v1/resource-center/stored-queries/{query_id}` |
| `update_stored_query` | Update an advanced query | WRITE | `PUT /v1/resource-center/stored-queries/{query_id}` |
| `delete_stored_query` | Delete an advanced query (confirm) | DANGEROUS | `DELETE /v1/resource-center/stored-queries/{query_id}` |

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
cd huaweicloud-mcp/server/mcp_server_rc
uv sync
uv run mcp-huaweicloud-rc          # stdio (default)
uv run mcp-huaweicloud-rc -t streamable-http
```

## Configuration

### Environment Variables

| Variable | Required | Description | Default |
|---|---|---|---|
| `HUAWEICLOUD_ACCESS_KEY` | Yes | Account access key (AK) | - |
| `HUAWEICLOUD_SECRET_KEY` | Yes | Account secret key (SK) | - |
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

### Protection-list caveat

The guardrail protection list matches at the **parameter level**. A resource
that carries a protection tag in the cloud but whose tag is not present in the
call arguments cannot be caught by the middleware first line — the DANGEROUS
tools therefore call `assert_not_protected` with the RC cloud-side real
attributes (id/name) as a second defense line. Note that resource groups and
advanced queries have **no tag dimension**: tag-based protection rules never
match them, so protect them by ID or name. Configure protection proactively
via the env vars or `guardrails.yaml`.

Example `guardrails.yaml`:

```yaml
version: 1
rules:
  - id: protect-prod-rc
    match:
      tools: ["delete_resource_group"]
      risks: [DANGEROUS]
      resources:
        name_patterns: ["^prod-"]
    action: block
    message: Production RC resources are protected. Contact the ops team.
```

### Run with uvx (from git)

```json
{
    "mcpServers": {
        "huaweicloud-rc": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/huaweicloud/huaweicloud-mcp#subdirectory=server/mcp_server_rc",
                "mcp-huaweicloud-rc"
            ],
            "env": {
                "HUAWEICLOUD_ACCESS_KEY": "",
                "HUAWEICLOUD_SECRET_KEY": ""
            }
        }
    }
}
```

## Examples

### Cursor / Claude Desktop / Trae

Add the JSON snippet above to your MCP client configuration, fill in the
credentials, then ask naturally:

- "List all resources" → `list_all_resources()`
- "Show the detail of resource your_resource_id" → `show_resource_detail(resource_id="your_resource_id")`
- "Query resources in region cn-north-4 of type ecs.cloudservers" → `list_all_resources(region_id="cn-north-4", resource_type="ecs.cloudservers")`
- "Which cloud services can be queried" → `list_providers()`
- "What tags do my resources have" → `list_all_tags()`
- "Create a resource group named prod" → `create_resource_group(group_name="prod")`
- "Add your_resource_id to the prod group" → `add_resources_to_group(group_id="<group_id>", resource_ids=["your_resource_id"])`
- "Delete the prod resource group" → `delete_resource_group(group_id="<group_id>")` (returns a preview first; call again with `confirm=true` to execute)
- "Which resources is your_resource_id related to" → `show_resource_relations(resource_id="your_resource_id")`
- "Run an advanced query: SELECT * FROM resources WHERE provider = 'ecs'" → `run_query(expression="SELECT * FROM resources WHERE provider = 'ecs'")`
- "Create an advanced query named my-ecs with expression SELECT * FROM resources WHERE provider = 'ecs'" → `create_stored_query(name="my-ecs", expression="SELECT * FROM resources WHERE provider = 'ecs'")`

## License

MIT
