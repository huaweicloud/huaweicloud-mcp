# 00 · 总览与导读

> huaweicloud-mcp 开发者文档。本文档与代码冲突时以源码为准。

## 这个项目是什么

`huaweicloud-mcp` 是一个华为云服务的 MCP Server 共享仓库。每个服务是一个独立可发布的包（`mcp-server-huaweicloud-<service>`），由 MCP 客户端（Cursor / Claude Desktop / Trae / 自研 Agent）加载，通过**场景化工具**驱动该云服务。

## 你应该先知道的三个事实

1. **工具不是 OpenAPI 透传**。本项目是场景化粗粒度——一个用户意图一个工具，内部可编排多个 API。详见 [03-tools.md](03-tools.md)。
2. **安全护栏自动开启**。`build_server()` 自动装配 `GuardrailsMiddleware`：风险分级校验、保护名单、输出脱敏、结构化审计，服务零代码获得。详见 [05-guardrails.md](05-guardrails.md)。
3. **强制三层架构**。`tools → service → client`，单向依赖，无跨层 import。详见 [01-architecture.md](01-architecture.md)。

## 读者画像

本套文档假设你：熟 Python + async + pytest，**但不熟** MCP 协议和华为云 SDK。前置知识我们补：
- MCP 是什么（[01-architecture.md](01-architecture.md) §1.2）
- huaweicloudsdk 是同步 SDK，async 工具怎么桥接（[04-service-client.md](04-service-client.md) §4.2）
- project_id / region 是什么（[02-core.md](02-core.md) §2.4）

## 阅读路径

| 你是 | 推荐路径 |
|---|---|
| 第一次接触本项目 | 00（本文）→ 01 → 02 → 08（从零建一个，动手跑 VPC） |
| 要写新服务 | 08（实战全程）← 回查 03/04/05/07 |
| 要改核心包 | 02 → 05 → 核心包源码 |
| 要加测试 | 07（三层测试，贴 RFS/VPC 真实代码） |
| 要发布 | 09（工程化与发布） |

## 快速验证一个服务

```bash
cd server/mcp_server_vpc          # 或 server/mcp_server_rfs
uv sync
export HUAWEICLOUD_ACCESS_KEY=... HUAWEICLOUD_SECRET_KEY=... HUAWEICLOUD_REGION=cn-north-4
uv run mcp-server-huaweicloud-vpc
uv run pytest --cov                # ruff / mypy / pytest 详见 09
```

## 文档索引

见 [README.md](README.md)（本目录索引页 + 治理声明）。
