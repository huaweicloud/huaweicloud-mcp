# ECS Lifecycle MCP Server（弹性云服务器生命周期）

> **语言切换：** [English](./README_en.md) | 中文

## 版本

0.1.0

## 概述

华为云 ECS（Elastic Cloud Server，弹性云服务器）生命周期操作的 MCP Server。让 MCP
客户端通过场景化工具创建、修改、删除云服务器，并跟踪异步任务进度。所有变更类
工具都遵循严格的两段式确认协议：第一次调用只返回预览（将要发生什么），必须显式传 `confirm=true` 才会真正执行——agent 绝不自作主张。

创建是意图驱动的：先用推导工具挑镜像 / 规格 / 密钥对（也可以全跳过——网络、
磁盘类型、安全组走智能默认兜底），预览里展示完整解析后的配置，确认后才真正下单。

## 分类

计算 / 弹性云服务器

## 功能

- 创建包周期（包月/包年）云服务器，返回订单号与任务号
- 创建按需（按量付费）云服务器，创建成功即按秒计费
- 批量删除云服务器，可显式控制数据盘与弹性公网 IP 的去留
- 修改云服务器的名称 / 描述 / 主机名
- 查询单台云服务器详情，或按名称 / 状态过滤列表
- 通过任务状态接口跟踪异步创建 / 删除进度
- 查询公共镜像（按名称关键字 / 操作系统）、规格（按 vCPU / 内存 GB）、SSH 密钥对
  ——意图驱动创建的推导依据（"帮我开一台跑 Redis 的测试机，最便宜就行"）
- 创建智能默认：`vpc_id` / `subnet_id` / `root_volume_type` 不填由服务端兜底，
  预览通过 `defaults_applied` 明示每一个兜底结果
- 常用槽位：`user_data`（启动脚本原文，自动 base64）、`security_group_id`、
  `eip_bandwidth`（自动分配 EIP，按流量计费）
- 所有变更工具执行两段式确认：先预览，传 `confirm=true` 才执行
- 第二防线：执行前用真实云属性（id/名称/标签）复查保护规则（环境变量或
  `guardrails.yaml`），受保护资源一律拦截

## 工具清单

| 工具 | 场景 | 风险级别 | API 文档 |
|---|---|---|---|
| `list_servers` | 实例清单，按名称 / 状态过滤 | READ | [ListServersDetails](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0094148850.html) |
| `show_server` | 单台实例完整详情 | READ | [ShowServer](https://support.huaweicloud.com/api-ecs/ecs_02_0104.html) |
| `show_job` | 跟踪异步创建 / 删除任务 | READ | [ShowJob](https://support.huaweicloud.com/api-ecs/ecs_02_0901.html) |
| `list_images` | 按名称关键字 / 操作系统浏览镜像 | READ | [ListImages](https://support.huaweicloud.com/api-ims/ims_03_0602.html) |
| `list_flavors` | 按 vCPU / 内存 GB 浏览规格，或按规格 ID 精确查询 | READ | [ListFlavors](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0020212656.html) |
| `list_keypairs` | 列出已有 SSH 密钥对 | READ | [NovaListKeypairs](https://support.huaweicloud.com/api-ecs/ecs_03_1201.html) |
| `create_server` | 创建包周期（包月/包年）云服务器 | WRITE | [CreateServers](https://support.huaweicloud.com/api-ecs/ecs_02_0101.html) |
| `create_on_demand_server` | 创建按需（按量付费）云服务器 | WRITE | [CreatePostPaidServers](https://support.huaweicloud.com/api-ecs/zh-cn_topic_0020212668.html) |
| `update_server` | 修改名称 / 描述 / 主机名 | WRITE | [UpdateServer](https://support.huaweicloud.com/api-ecs/ecs_02_0106.html) |
| `delete_servers` | 删除一台或多台云服务器 | DANGEROUS | [DeleteServers](https://support.huaweicloud.com/api-ecs/ecs_02_0103.html) |

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
cd huaweicloud-mcp/server/mcp_server_ecs_lifecycle
uv sync
uv run mcp-server-ecs-lifecycle          # stdio（默认）
uv run mcp-server-ecs-lifecycle -t streamable-http
```

## 配置

### 环境变量

| 变量 | 必填 | 说明 | 默认值 |
|---|---|---|---|
| `HUAWEICLOUD_ACCESS_KEY` | 是 | 账号 AK | - |
| `HUAWEICLOUD_SECRET_KEY` | 是 | 账号 SK | - |
| `HUAWEICLOUD_REGION` | 是 | 资源所在区域（如 `cn-north-4`） | - |
| `HUAWEICLOUD_PROJECT_ID` | 否 | 手动覆盖 project_id（默认经 IAM 自动解析） | 自动解析 |
| `HUAWEICLOUD_ENDPOINT` | 否 | 覆盖 ECS 接入点；IMS/VPC 接入点自动派生（`ecs.` 首标签替换为 `ims.`/`vpc.`、网关型 host 全服务复用，SDK region 表之外的区域按 `https://ecs.<region>.myhuaweicloud.com` 合成） | 自动派生 |
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

**两段式确认协议（变更类工具）：** `create_server`、`create_on_demand_server`、
`update_server`、`delete_servers` 都是需要两次调用的工具。`confirm=false`
（默认）时只返回预览、不做任何变更；`confirm=true` 时才执行。执行前会把每个
目标服务器按真实云属性（id/名称/标签）再过一遍保护规则
（HUAWEICLOUD_MCP_PROTECTED_* 或 guardrails.yaml），命中即返回
`MCP_GUARDRAIL_BLOCKED`。

**删除的安全默认值：** `delete_servers` 默认保留数据盘（仅卸载）、保留弹性公网
IP（仅解绑），除非显式传入 `delete_volume=true` / `delete_publicip=true` 并确认。
删除后云服务器不可恢复。

**创建智能默认：** `vpc_id` / `subnet_id` / `root_volume_type` 均可选。不填时
服务端实时兜底：取区域内按名称排序的第一个子网（同时确定 VPC），系统盘默认
`SSD`。预览的 `defaults_applied` 会列全所有兜底项，并展示命中子网的名称与网段，
确认时看到的就是真实生效值。区域内无子网（或 `subnet_id` 未知）时创建失败并
返回 `MCP_NOT_FOUND`，此时请显式传 ID。不传 `security_group_id` 时由 API 挂
默认安全组；不传 `eip_bandwidth` 时不分配公网 IP。

### uvx 运行

PyPI 版本：

```json
{
    "mcpServers": {
        "huaweicloud-ecs-lifecycle": {
            "command": "uvx",
            "args": ["mcp-server-ecs-lifecycle"],
            "env": {
                "HUAWEICLOUD_ACCESS_KEY": "",
                "HUAWEICLOUD_SECRET_KEY": "",
                "HUAWEICLOUD_REGION": ""
            }
        }
    }
}
```

git 仓库版本：

```json
{
    "mcpServers": {
        "huaweicloud-ecs-lifecycle": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/<org>/huaweicloud-mcp#subdirectory=server/mcp_server_ecs_lifecycle",
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

## 示例

### Cursor / Claude Desktop / Trae

将上述 JSON 配置填入 MCP 客户端并填入凭证，然后自然语言使用：

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

## 许可证

MIT
