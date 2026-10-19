# RFS MCP Server（资源编排服务）

> **语言切换：** [English](./README_en.md) | 中文

## 版本

0.1.0

## 概述

华为云 RFS（Resource Formation Service，资源编排服务）的 MCP Server。让 MCP 客户端
通过场景化工具管理基础设施即代码：部署 HCL 模板为资源栈、执行计划干跑预览变更、
诊断失败部署、安全下线资源栈。

## 分类

管理与治理 / 基础设施即代码

## 功能

- 部署 HCL 模板（内联文本或 OBS 地址）为 RFS 资源栈——自动创建或更新
- 通过执行计划干跑模板变更（新增 / 删除 / 变更差异）
- 诊断失败或卡住的栈：聚合状态、失败事件、失败资源、根因结论
- 分页查询资源栈清单
- 读取栈元数据与输出
- 删除栈：显式确认流程 + 资源预览

## 工具清单

| 工具 | 场景 | 风险级别 | API 文档 |
|---|---|---|---|
| `list_stacks` | 栈清单查询、按名称过滤 | READ | [ListStacks](https://support.huaweicloud.com/api-rfs/rfs_02_0031.html) |
| `get_stack` | 栈元数据 + 输出值 | READ | [GetStackMetadata](https://support.huaweicloud.com/api-rfs/rfs_02_0033.html) / [ListStackOutputs](https://support.huaweicloud.com/api-rfs/rfs_02_0041.html) |
| `preview_stack_changes` | 部署前干跑变更差异 | READ | [CreateExecutionPlan](https://support.huaweicloud.com/api-rfs/rfs_02_0051.html) / [GetExecutionPlan](https://support.huaweicloud.com/api-rfs/rfs_02_0053.html) |
| `deploy_stack` | 从模板创建或更新栈 | WRITE | [CreateStack](https://support.huaweicloud.com/api-rfs/rfs_02_0021.html) / [DeployStack](https://support.huaweicloud.com/api-rfs/rfs_02_0027.html) |
| `diagnose_stack` | 定位部署失败根因 | READ | [ListStackEvents](https://support.huaweicloud.com/api-rfs/rfs_02_0037.html) / [ListStackResources](https://support.huaweicloud.com/api-rfs/rfs_02_0039.html) |
| `delete_stack` | 下线资源栈（需确认） | DANGEROUS | [DeleteStack](https://support.huaweicloud.com/api-rfs/rfs_02_0029.html) |

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
cd huaweicloud-mcp/server/mcp_server_rfs
uv sync
uv run mcp-huaweicloud-rfs          # stdio（默认）
uv run mcp-huaweicloud-rfs -t streamable-http
```

## 配置

### 环境变量

| 变量 | 必填 | 说明 | 默认值 |
|---|---|---|---|
| `HUAWEICLOUD_ACCESS_KEY` | 是 | 账号 AK | - |
| `HUAWEICLOUD_SECRET_KEY` | 是 | 账号 SK | - |
| `HUAWEICLOUD_REGION` | 是 | 资源所在区域（如 `cn-north-4`） | - |
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

**护栏已知局限（参数级匹配）：** 保护规则匹配工具参数中的资源 ID、名称类参数、显式
传入的标签。仅在云侧打保护标签而参数中未出现的资源，由第二道防线兜底：`delete_stack`
在执行不可逆操作前会用栈的真实属性再次校验。

### uvx 运行

git 仓库版本：

```json
{
    "mcpServers": {
        "huaweicloud-rfs": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/huaweicloud/huaweicloud-mcp#subdirectory=server/mcp_server_rfs",
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

## 示例

### Cursor / Claude Desktop / Trae

将上述 JSON 配置填入 MCP 客户端并填入凭证，然后自然语言使用：

- "帮我把这个 HCL 模板部署成名为 web-app 的资源栈" → `deploy_stack`
- "web-app 栈部署失败了，帮我看看原因" → `diagnose_stack`
- "预览一下模板改动会影响哪些资源" → `preview_stack_changes`
- "删掉 web-app 这个栈" → `delete_stack`（先返回预览，确认后执行）

## 许可证

MIT
