# ECS Readonly MCP Server（弹性云服务器只读）

> **语言切换：** [English](./README_en.md) | 中文

## 版本

0.1.0

## 概述

华为云 ECS（Elastic Cloud Server，弹性云服务器）的只读 MCP Server。让 MCP 客户端通过
场景化工具审计云服务器使用情况：统计实例数量、分解开关机状态、盘点规格用量、
汇总运行中实例的 vCPU/内存、审查公网/私网 IP 使用——面向 AI agent 的周期性
资源盘点场景设计。

## 分类

计算 / 弹性云服务器

## 功能

- 查询云服务器列表，支持按名称 / 状态 / 规格过滤
- 统计实例总数，或按电源状态分组计数（ACTIVE / SHUTOFF / ERROR...）
- 盘点实例规格及每种规格的台数
- 汇总运行中实例的 vCPU 总数与内存总量（GB）
- 统计全量实例的公网 / 私网 IP 使用情况
- 只读：所有工具均声明 READ 风险级别，无任何破坏性操作

## 工具清单

| 工具 | 场景 | 风险级别 | API 文档 |
|---|---|---|---|
| `list_servers` | 实例清单，按名称 / 状态 / 规格过滤 | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `count_servers` | 实例总数 | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `count_servers_by_status` | 按电源状态分组计数 | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `list_server_flavors` | 规格盘点及各规格台数 | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `analyze_server_resources` | 运行实例 vCPU / 内存汇总 | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `analyze_server_ips` | 公网 / 私网 IP 使用情况 | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |

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

## 配置

### 环境变量

| 变量 | 必填 | 说明 | 默认值 |
|---|---|---|---|
| `HUAWEICLOUD_ACCESS_KEY` | 是 | 账号 AK | - |
| `HUAWEICLOUD_SECRET_KEY` | 是 | 账号 SK | - |
| `HUAWEICLOUD_REGION` | 是 | 资源所在区域（如 `cn-north-4`） | - |
| `HUAWEICLOUD_PROJECT_ID` | 是 | 资源所在项目的 project_id（控制台：我的凭证 > 项目列表，形如 `0610f92e7d124d4a9e4d8e8d95b4a4d0`） | - |
| `HUAWEICLOUD_ENDPOINT` | 否 | 覆盖 ECS 接入点（SDK region 表之外的区域会自动按 `https://ecs.<region>.myhuaweicloud.com` 合成） | 自动合成 |
| `HUAWEICLOUD_SECURITY_TOKEN` | 否 | STS 临时凭证 token | - |
| `HUAWEICLOUD_MCP_READ_ONLY` | 否 | `true` 拦截所有 WRITE/DANGEROUS 工具 | `false` |
| `HUAWEICLOUD_MCP_PROTECTED_IDS` | 否 | 护栏：受保护资源 ID（逗号分隔，命中即 block） | 空 |
| `HUAWEICLOUD_MCP_PROTECTED_NAMES` | 否 | 护栏：受保护资源名称（逗号分隔，命中即 block） | 空 |
| `HUAWEICLOUD_MCP_PROTECTED_TAGS` | 否 | 护栏：受保护标签（逗号分隔 `k` 或 `k=v`） | 空 |
| `HUAWEICLOUD_MCP_GUARDRAILS_CONFIG` | 否 | 复杂规则文件 `guardrails.yaml` 路径 | 空 |
| `HUAWEICLOUD_MCP_AUDIT_FILE` | 否 | 审计 JSONL 文件路径（审计始终开启，默认写 stderr） | 空 |
| `HUAWEICLOUD_MCP_MAX_CONCURRENT` | 否 | SDK 并发上限（进程级信号量）；超出的调用排队，默认 20 | `20` |
| `MCP_SERVER_PORT` | 否 | streamable-http 端口 | `8000` |
| `MCP_SERVER_HOST` | 否 | streamable-http 绑定地址 | `0.0.0.0` |

**护栏已知局限（参数级匹配）：** 保护规则匹配工具参数中的资源 ID、名称类参数、
显式传入的标签。本服务器为纯只读——不暴露任何删除/关机/重建类工具——因此保护
护栏在本服务中主要承担输出脱敏与审计职责，而非写操作拦截。

### 运行

#### 方式一：以 stdio 协议运行（推荐本地使用）

由 Agent 直接拉起本地进程，无需手动启动服务。以 OpenCode 为例：

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

将 `HUAWEICLOUD_ACCESS_KEY`、`HUAWEICLOUD_SECRET_KEY` 替换为实际值；生产环境建议锁定具体版本号，而非使用 `@latest`。

#### 方式二：以 Streamable HTTP 服务方式运行

适用于远程部署或多客户端共享同一服务的场景。

1. 获取代码并启动服务

```bash
git clone https://github.com/huaweicloud/huaweicloud-mcp.git
cd huaweicloud-mcp/server/mcp_huaweicloud_ecs_readonly
uv sync
uv run mcp-huaweicloud-ecs-readonly -t streamable-http   # 默认监听 8000 端口
```

服务启动后，MCP 端点地址为 http://127.0.0.1:8000/mcp。

2. 在 Agent 中配置 MCP

以 OpenCode 为例：

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

3. 验证

配置完成后重启 Agent，确认 MCP Server 处于已连接状态，并可正常调用 ECS 只读相关工具。

注意事项
- 不同 Agent 的配置字段存在差异（例如 mcpServers / mcp、environment / env），具体请以对应 Agent 的官方文档为准。
- 建议通过环境变量注入 AK/SK，避免将密钥明文写入配置文件并提交至代码仓库。
- 选择建议：本地开发调试优先使用 stdio；需要远程访问或多客户端共享时使用 Streamable HTTP。

## 示例

### Cursor / Claude Desktop / Trae

将上述 JSON 配置填入 MCP 客户端并填入凭证，然后自然语言使用：

- "我们一共有多少台云服务器？" → `count_servers`
- "有多少机器在跑，多少关着的？" → `count_servers_by_status`
- "都用了哪些规格，每种几台？" → `list_server_flavors`
- "运行中的机器一共多少核、多少内存？" → `analyze_server_resources`
- "哪些机器挂了公网 IP？" → `analyze_server_ips`
- "列一下名字带 web 的运行中的机器" → `list_servers`

## 许可证

MIT
