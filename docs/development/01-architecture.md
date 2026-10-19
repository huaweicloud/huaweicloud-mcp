# 01 · 总体架构

## 1.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     MCP Client (LLM 侧)                     │
│        Cursor / Claude Desktop / Trae / 自研 Agent           │
└───────────────┬─────────────────────────┬───────────────────┘
        stdio (本地默认)          streamable-http (远程)
                 │                         │
┌───────────────▼─────────────────────────▼───────────────────┐
│              server/mcp_server_<service>                │
│                                                              │
│  tools/      场景工具层：@server.tool() 注册、参数校验、       │
│              @guard 风险分级声明（拦截由 middleware 执行）、    │
│              输出整形                                        │
│    │                                                         │
│  service/    编排层：业务逻辑、多 API 组合、分页、聚合        │
│    │                                                         │
│  client/     SDK 封装层：构建 Client、调 API、异常映射        │
└────┼─────────────────────────────────────────────────────────┘
     │ 依赖
┌────▼─────────────────────────────────────────────────────────┐
│  libs/huaweicloud_mcp_core  (PyPI: huaweicloud-mcp-core)     │
│  config / credentials / errors / security / output / server  │
│  guardrails (rules / protect / masking / audit / middleware) │
└────┬─────────────────────────────────────────────────────────┘
     │
┌────▼─────────────────────────────────────────────────────────┐
│   huaweicloudsdk-core + huaweicloudsdk-<service> (官方 SDK)  │
│              华为云 OpenAPI (签名 / project_id / 重试)        │
└──────────────────────────────────────────────────────────────┘
```

## 1.2 MCP 是什么（给不熟的读者）

MCP（Model Context Protocol）是 LLM 与外部工具/数据源通信的协议。MCP Server 暴露一组"工具"（tool），每个工具有名字、参数 schema、描述；MCP Client（带 LLM 的应用）调用工具，拿到结构化结果，喂给 LLM 推理。

- 传输：`stdio`（本地，进程标准输入输出承载 JSON-RPC）或 `streamable-http`（远程，HTTP）。本项目两种都支持，核心包 `run_standard` 统一 argparse 选。
- 工具是 async 函数，`@mcp.tool()` 注册；mcp 2.x 的 `MCPServer` 负责协议握手。
- 中间件（`ServerMiddleware`）可包裹所有入站请求——本项目用它做护栏。

## 1.3 技术决策总览

| 决策项 | 结论                                                                           |
|---|------------------------------------------------------------------------------|
| 语言 | Python，最低 **3.10**                                                           |
| MCP SDK | 官方 `mcp` **2.x**（`MCPServer`；mcp 2.x 起 FastMCP 已更名）                          |
| 云 API 调用 | 华为云官方 SDK（`huaweicloudsdk-core` + `huaweicloudsdk-<service>`，同步）             |
| 仓库结构 | Monorepo：`server/mcp_server_<service>/`，每服务独立可发布包                            |
| 公共能力 | 共享核心包 `libs/huaweicloud_mcp_core`（独立发布 `huaweicloud-mcp-core`）               |
| 认证 | 环境变量 + project_id 由核心包调 IAM 自动解析，支持手动覆盖                                      |
| STS 临时凭证 | 可选支持（`HUAWEICLOUD_SECURITY_TOKEN`）                                           |
| 传输协议 | stdio（默认）+ streamable-http，**必须**同时支持                                        |
| 工具粒度 | **场景化粗粒度**（一个用户意图一个工具，可编排多个 API）                                             |
| 代码分层 | **强制三层**：tools → service → client                                            |
| 安全 | READ/WRITE/DANGEROUS 分级 + confirm + 只读模式 + **护栏**（保护名单/脱敏/审计，middleware 自动装） |
| 输出 | 结构化 JSON + token 预算（默认 20 条、字段截断、分页）                                         |
| 工程化 | uv + ruff + mypy（strict）+ pytest（覆盖率 ≥ 80%）+ CI 全绿才可合入                       |
| 文档 | 双语 README，固定章节模板                                                             |
| 发布 | 源码 git subdirectory 方式使用                                                     |

## 1.4 仓库布局

```
huaweicloud-mcp/
├── docs/development/                  # 开发者文档（本目录）+ 脚手架模板 template/
├── server/                           # 所有服务的 MCP Server
│   ├── mcp_server_rfs/          # 参考实现（完整测试）
│   ├── mcp_server_vpc/          # 参考实现（实战篇产物）
│   └── mcp_server_<service>/
│       ├── pyproject.toml            # 独立可发布包
│       ├── uv.lock
│       ├── README.md / README_zh.md  # 双语（必需）
│       ├── src/mcp_server_<service>/
│       │   ├── main.py               # 入口
│       │   ├── server.py             # MCPServer 构建（build_server）
│       │   ├── tools/                # 第 1 层
│       │   ├── service/              # 第 2 层
│       │   └── client/               # 第 3 层
│       └── tests/                    # 与 src 平级
├── libs/
│   └── huaweicloud_mcp_core/         # 公共核心包（含 tests、py.typed）
├── DEVELOPMENT.md                   # 迁移索引页（指向本目录）
├── DEVELOPMENT_SPEC2.md              # 旧单文件规范（备份，见 docs/development/README.md）
├── README.md / README_zh.md
└── LICENSE
```

## 1.5 三层架构（强制）

每个服务**必须**严格三层，层间依赖单向：`tools → service → client`。

| 层 | 目录 | 职责 | 禁止 |
|---|---|---|---|
| **tools** | `tools/` | `@server.tool()` 注册；参数类型与 docstring；调 service；`@guard` 风险分级声明；输出整形 | 直接 import `huaweicloudsdk*`；写业务逻辑 |
| **service** | `service/` | 业务逻辑；组合多个 client 调用；分页与聚合；字段白名单裁剪；confirm 分支；护栏第二防线 | 直接构建 SDK Client；感知 MCP 框架 |
| **client** | `client/` | 构建 SDK Client（凭证、region、endpoint、超时）；薄封装每个 API；异常透传 | 业务逻辑；修改返回结构 |

规则：
1. tools 按资源域分文件（`tools/instance.py`、`tools/image.py`），单文件超 500 行**应当**拆分。
2. client 层函数签名**应当**与 OpenAPI action 一一对应并保留原名（如 `list_servers_details`），便于追溯与测试。
3. service 层函数返回**必须**是纯 dict/list（已裁剪），不返回 SDK response 对象。

详见 [04-service-client.md](04-service-client.md)。

## 1.6 命名规范（必须）

| 对象 | 规则 | 示例 |
|---|---|---|
| 服务目录 | `mcp_server_<service>`，连字符分隔 | `mcp_server_ecs`、`mcp_server_rds_mysql` |
| Python 包名（import） | `mcp_server_<service>`，下划线分隔 | `mcp_server_ecs` |
| 可执行命令 | 与服务目录一致 | `mcp_server_ecs` |
| MCP server name | `huaweicloud-<service>` | `MCPServer("huaweicloud-ecs")`（build_server 生成） |
| 服务名取值 | 与控制台产品名对应，多单词用连字符 | `rds-mysql`、`gaussdb`、`functiongraph` |

**禁止**：同一服务拆成多个包；目录名与 dist 名、import 名不一致。

> 分发名（`mcp_server_ecs`）与导入名（`mcp_server_ecs`）不一致，hatchling 无法自动定位包——pyproject **必须**显式配置 `[tool.hatch.build.targets.wheel] packages = ["src/mcp_server_ecs"]`。

下一站：[02-core.md](02-core.md) 讲核心包。
