# 华为云 MCP Server 开发规范（已迁移）

> **本文件已降级为索引页。** 完整开发规范已按功能特性拆分到 [`docs/development/`](docs/development/README.md) 目录，并补充手把手教程与样例。本文仅保留迁移说明与对外入口。

## 去哪里读

**开发者文档主入口**：[`docs/development/README.md`](docs/development/README.md)

各主题速查：

| 原 spec 章节 | 迁移至 |
|---|---|
| §1 总体架构 / §2 仓库布局 / §4 三层架构 | [`docs/development/01-architecture.md`](docs/development/01-architecture.md) |
| §3 公共核心包 / §9 认证配置 / §7 护栏 / §8 输出错误 | [`docs/development/02-core.md`](docs/development/02-core.md) |
| §6 工具设计 / §7.2 风险分级 / §7.9 强制机制 | [`docs/development/03-tools.md`](docs/development/03-tools.md) |
| §5.5/5.6 service/client 模板 | [`docs/development/04-service-client.md`](docs/development/04-service-client.md) |
| §7 安全护栏 | [`docs/development/05-guardrails.md`](docs/development/05-guardrails.md) |
| §8 输出与错误处理 | [`docs/development/06-output-errors.md`](docs/development/06-output-errors.md) |
| §11.3/11.4 测试与 CI 自检 | [`docs/development/07-testing.md`](docs/development/07-testing.md) |
| §5/§13 代码模板与新服务接入流程 | [`docs/development/08-new-service-walkthrough.md`](docs/development/08-new-service-walkthrough.md) |
| §11 工程化 / §14 发布 / §12 文档 / §10 传输 | [`docs/development/09-engineering-release.md`](docs/development/09-engineering-release.md) |
| 总览与导读 | [`docs/development/00-overview.md`](docs/development/00-overview.md) |

## 治理声明

- 文档与代码冲突时，以源码为准。
- 每篇顶部标注"对应原规范条文"，便于追溯条文依据。
- 本套文档不加 CI 检查；依赖人工评审与 PR 审查保持同步。
