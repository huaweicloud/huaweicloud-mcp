# RC MCP Server（资源中心）

> **语言切换：** [English](./README_en.md) | 中文

## 版本

0.1.0

## 概述

华为云资源中心（Resource Center，简称 RC）MCP Server，为用户提供全局
资源管理能力。用户可以通过 RC 检索自己在云平台上的资源，查看资源详情、
资源之间的关系，还可以对资源进行分组管理。同时支持自定义高级查询，通过
使用 ResourceQL 查询特定条件下的资源配置状态。

## 分类

管理与治理 / 资源中心

## 功能

**资源查询（Resource Query）**

- 查看所有资源列表，支持按资源名称、资源 ID、标签、企业项目、区域、
  资源类型等条件筛选
- 指定资源 ID，返回该资源的详细信息
- 列举 RC 支持的云服务、资源和区域列表

**资源关系（Resource Relationships）**

- 指定资源 ID，查询该资源与其他资源的关联关系

**资源分组（Resource Groups）**

- 创建、修改、删除、查询、列举资源分组
- 向分组批量添加资源、从分组移除资源

**高级查询（Advanced Queries）**

- 运行高级查询（ResourceQL）
- 高级查询（存储查询）的增、删、改、查

**通用能力**

- 结构化 JSON 输出，支持分页和字段白名单裁剪
- 通过环境变量进行 AK/SK 鉴权（使用共享核心包）
- 安全护栏自动开启（风险声明、输出脱敏、结构化审计）

## 工具清单

| 工具 | 场景 | 风险级别 | API |
|---|---|---|---|
| `list_providers` | 列出所有云服务提供商 | READ | `GET /v1/resource-center/all-providers` |
| `list_all_resources` | 按条件列出所有资源 | READ | `GET /v1/resource-center/all-resources` |
| `show_resource_detail` | 按 ID 查询单个资源详情 | READ | `GET /v1/resource-center/all-resources/{resource_id}` |
| `list_all_tags` | 列出所有资源标签 | READ | `GET /v1/resource-center/all-resources/tags` |
| `count_all_resources` | 按条件统计资源数量 | READ | `GET /v1/resource-center/all-resources/count` |
| `collect_resources_summary` | 按服务/类型/区域汇总资源 | READ | `GET /v1/resource-center/all-resources/summary` |
| `create_resource_group` | 创建资源分组 | WRITE | `POST /v1/resource-center/groups` |
| `update_resource_group` | 修改资源分组描述 | WRITE | `PATCH /v1/resource-center/groups/{group_id}` |
| `delete_resource_group` | 删除资源分组（需确认） | DANGEROUS | `DELETE /v1/resource-center/groups/{group_id}` |
| `show_resource_group` | 查询单个资源分组 | READ | `GET /v1/resource-center/groups/{group_id}` |
| `list_resource_groups` | 查询资源分组列表 | READ | `GET /v1/resource-center/groups` |
| `add_resources_to_group` | 向资源分组添加资源 | WRITE | `PUT /v1/resource-center/groups/{group_id}/resources` |
| `remove_resource_from_group` | 从资源分组移除资源 | WRITE | `DELETE /v1/resource-center/groups/{group_id}/resources/{resource_id}` |
| `show_resource_relations` | 查询资源关联关系 | READ | `GET /v1/resource-center/resource-relations` |
| `run_query` | 执行高级查询 | READ | `POST /v1/resource-center/run-query` |
| `create_stored_query` | 创建高级查询 | WRITE | `POST /v1/resource-center/stored-queries` |
| `list_stored_queries` | 列举高级查询 | READ | `GET /v1/resource-center/stored-queries` |
| `show_stored_query` | 查询高级查询详情 | READ | `GET /v1/resource-center/stored-queries/{query_id}` |
| `update_stored_query` | 更新高级查询 | WRITE | `PUT /v1/resource-center/stored-queries/{query_id}` |
| `delete_stored_query` | 删除高级查询（需确认） | DANGEROUS | `DELETE /v1/resource-center/stored-queries/{query_id}` |

## 使用指引

### 前置条件

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

### 安装

```bash
git clone <仓库地址>
cd huaweicloud-mcp/server/mcp_server_rc
uv sync
uv run mcp-huaweicloud-rc          # stdio（默认）
uv run mcp-huaweicloud-rc -t streamable-http
```

## 配置

### 环境变量

| 变量 | 必填 | 说明 | 默认值 |
|---|---|---|---|
| `HUAWEICLOUD_ACCESS_KEY` | 是 | 账号 AK | - |
| `HUAWEICLOUD_SECRET_KEY` | 是 | 账号 SK | - |
| `HUAWEICLOUD_PROJECT_ID` | 否 | 手动覆盖 project_id（默认经 IAM 自动解析） | 自动解析 |
| `HUAWEICLOUD_SECURITY_TOKEN` | 否 | STS 临时凭证 token | - |
| `HUAWEICLOUD_MCP_READ_ONLY` | 否 | `true` 拦截所有 WRITE/DANGEROUS 工具 | `false` |
| `HUAWEICLOUD_MCP_PROTECTED_IDS` | 否 | 护栏：受保护资源 ID（逗号分隔，命中即 block） | 空 |
| `HUAWEICLOUD_MCP_PROTECTED_NAMES` | 否 | 护栏：受保护资源名称（逗号分隔，命中即 block） | 空 |
| `HUAWEICLOUD_MCP_PROTECTED_TAGS` | 否 | 护栏：受保护标签（逗号分隔 `k` 或 `k=v`） | 空 |
| `HUAWEICLOUD_MCP_GUARDRAILS_CONFIG` | 否 | 复杂规则文件 `guardrails.yaml` 路径 | 空 |
| `HUAWEICLOUD_MCP_AUDIT_FILE` | 否 | 审计 JSONL 文件路径（审计始终开启，默认写 stderr） | 空 |
| `MCP_SERVER_PORT` | 否 | streamable-http 端口 | `8000` |
| `MCP_SERVER_HOST` | 否 | streamable-http 绑定地址 | `0.0.0.0` |

### 保护名单盲区声明

护栏保护名单为**参数级匹配**。云上打了保护标签、但本次调用参数中未出现
该标签的资源，参数级匹配无法命中——因此 DANGEROUS 工具在执行不可逆操作前
调用 `assert_not_protected`，用 RC 云上真实属性（id/name）做第二道防线。
注意：资源分组与高级查询**无标签维度**，基于标签的保护规则对其不生效，
请使用 ID/名称保护。建议通过环境变量或 `guardrails.yaml` 主动配置保护名单。

`guardrails.yaml` 示例：

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
    message: 生产 RC 受保护，请联系运维。
```

### uvx 运行（git 仓库版本）

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

## 示例

### Cursor / Claude Desktop / Trae

将上述 JSON 配置填入 MCP 客户端并填入凭证，然后自然语言使用：

- "列出所有资源" → `list_all_resources()`
- "查资源 your_resource_id 的详细信息" → `show_resource_detail(resource_id="your_resource_id")`
- "查询 region_id：cn-north-4，资源类型：ecs.cloudservers 的资源" → `list_all_resources(region_id="cn-north-4", resource_type="ecs.cloudservers")`
- "有哪些云服务可以查询" → `list_providers()`
- "我的资源有哪些标签" → `list_all_tags()`
- "创建一个叫 prod 的资源组" → `create_resource_group(group_name="prod")`
- "把 your_resource_id 加入 prod 组" → `add_resources_to_group(group_id="<group_id>", resource_ids=["your_resource_id"])`
- "删除 prod 资源组" → `delete_resource_group(group_id="<group_id>")`（先返回预览，确认后 `confirm=true`，执行）
- "资源 your_resource_id 都关联了哪些资源" → `show_resource_relations(resource_id="your_resource_id")`
- "运行高级查询，ResourceQL：SELECT * FROM resources WHERE provider = 'ecs'" → `run_query(expression="SELECT * FROM resources WHERE provider = 'ecs'")`
- "创建一个高级查询，名称：my-ecs，表达式：SELECT * FROM resources WHERE provider = 'ecs'" → `create_stored_query(name="my-ecs", expression="SELECT * FROM resources WHERE provider = 'ecs'")`

## 许可证

MIT
