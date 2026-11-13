# mcp-server-ecs-common

> **语言切换：** [English](./README_en.md) | 中文

华为云 ECS MCP Server 家族的共享工具库。本包服务于 **ecs-readonly**（`mcp_server_ecs_readonly`）与
**ecs-lifecycle**（`mcp_server_ecs_lifecycle`）两个 server 包，避免两者重复实现
SDK 响应转换与分页逻辑。

## 内容

- `sdk_to_dict(obj)` —— 递归将 `huaweicloudsdk` 响应对象转为纯 JSON 兼容数据
  （处理标量、bytes、dict、list、带 `to_dict()` 的对象，以及暴露 `__dict__` 的对象）。
- `paginate(fetch, *, result_key, page_size, max_pages=None, advance=None)` ——
  收集分页列表接口的全部条目，在 servers / flavors / subnets 等场景共用同一套分页
  循环骨架。
- `call_sdk(fn, ...)` —— 两个 server 共享的 SDK 调用流控层，替代
  `asyncio.to_thread`：进程级信号量限并发（`HUAWEICLOUD_MCP_MAX_CONCURRENT`，默认
  20），429/5xx 与传输层错误重试最多三次（固定退避 5s/10s/20s + 抖动），仍失败抛语义化错误码
  （`MCP_RATE_LIMITED` / `MCP_SERVER_ERROR` / `MCP_TRANSIENT_ERROR`，均带"不要立即
  重试"的 hint）。

## 开发

本包是 `mcp-server-ecs-readonly` 与 `mcp-server-ecs-lifecycle` 的本地路径依赖。除标准库外
无运行时依赖。

```bash
uv run pytest
```
