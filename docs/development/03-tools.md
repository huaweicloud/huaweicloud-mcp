# 03 · 工具层：场景化方法论与 @guard

> 参考实现：`server/mcp_server_rfs/src/mcp_server_rfs/tools/stack.py`。

## 3.1 工具层做什么、不做什么

`tools/` 是三层架构的最上层，职责只有三件：

| 该做 | 不该做 |
|---|---|
| `@mcp.tool()` 注册工具 | 直接 import `huaweicloudsdk*` |
| 参数类型与 docstring | 写业务逻辑 |
| `@guard(risk=...)` 声明风险级 | 修改返回结构（由 service 层裁剪） |
| 调 service 层、透传参数 | 感知 MCP 框架细节 |

一个工具函数应该极薄——校验由 service 做，编排由 service 做，工具只负责"把参数交给 service，把结果交还框架"。看 RFS 的 `list_stacks`：

```python
@mcp.tool()
@guard(risk=ToolRisk.READ)
async def list_stacks(name: str | None = None, limit: int = 20, marker: str | None = None) -> dict:
    """List RFS resource stacks in the current region.
    ...docstring...
    """
    return await StackService().list_stacks(name=name, limit=limit, marker=marker)
```

就这一行。所有"钳制 limit、调 client、字段裁剪、组装信封"都在 `StackService.list_stacks` 里。

## 3.2 什么是"场景化工具"（核心方法论）

本项目的工具**不是** OpenAPI 的逐一透传，而是**面向用户意图**的场景化工具：

- **一个工具 = 一个完整用户意图**：如"帮我扩容这台 ECS"、"分析这台 RDS 的慢日志"、"把这个 OBS 桶开放为静态网站"。
- 工具内部可编排 1..n 个 API 调用、校验、等待、回填，用户（LLM）一次调用得到可呈现结果。
- 粗粒度**不等于**参数堆砌：参数是意图的自然输入，不是 API 参数表的拼接。

对比 RFS 的设计：如果把 OpenAPI 透传，会有 `list_stacks` / `get_stack_metadata` / `list_stack_outputs` / `list_stack_resources` / `list_stack_events` 五个查询工具。RFS 把后三个收进 `get_stack`（元数据+输出）和 `diagnose_stack`（状态+失败事件+失败资源+根因结论），从 5 个低级查询收成 2 个有附加值的场景工具——LLM 调用链更短、出错率更低。

### 场景从哪里来（四个来源，都要看）

1. 华为云控制台该服务的高频操作入口（控制台菜单即场景地图）。
2. 官方文档"最佳实践 / 快速入门"中的端到端流程。
3. 高频工单 / FAQ 中的排查类诉求（诊断、分析类场景优先——天然只读、安全）。
4. 本服务 Agent 用户的目标任务（部署、巡检、成本优化等）。

## 3.3 粒度判据（必须全部满足）

| 规则 | 说明 |
|---|---|
| 单意图 | 工具名能补全句子"帮我 \_\_\_"，且句中只有一个动词 |
| 参数 ≤ 10 | 超过则拆分场景，或把低频参数折叠为可选 dict |
| 自包含 | 调用返回即可直接呈现/继续对话，不需要用户再手工补查 |
| 单服务 | 不跨华为云服务编排（跨服务由 MCP Client 侧组合多个 server） |
| 有附加值 | 只包一个 API 且无校验/裁剪/聚合的工具，应重新评估是否合并进场景工具 |

## 3.4 首发数量

首版 **5–15 个工具**。少于 5 个说明场景调研不足；多于 15 个会稀释 LLM 工具选择准确率，应分批。RFS 是 6 个工具（list_stacks / get_stack / preview_stack_changes / deploy_stack / diagnose_stack / delete_stack），正好在区间内。

## 3.5 命名（必须）

- `snake_case`，格式 `动词_对象[_限定]`，总长 ≤ 40 字符。
- 动词从推荐表选取（可扩展，PR 审查把关）：

| 动词 | 语义 | 典型风险级 |
|---|---|---|
| list / get | 查询列表 / 详情 | READ |
| query | 条件查询、组合查询 | READ |
| analyze / diagnose | 分析、诊断（含推理结论） | READ |
| compare | 对比 | READ |
| create / deploy / enable | 创建、部署、开通 | WRITE |
| update / modify / config | 变更配置 | WRITE |
| resize / scale | 扩缩容 | WRITE |
| renew | 续订 | WRITE |
| stop / start / restart | 生命周期操作 | WRITE |
| delete / release / destroy | 删除、释放（不可逆） | DANGEROUS |
| clean / reset | 清理、重置（数据影响） | DANGEROUS |

- 对象名用资源单数或场景名：`resize_instance_flavor`、`analyze_slow_sql`、`configure_static_website`。
- **禁止**：`handle_xxx` / `do_xxx` / `xxx_v2` / 通用名如 `execute_api`。

## 3.6 描述与参数（必须）

工具 docstring 用**英文**书写（LLM 与国际生态兼容，spec §6.6 强制），结构固定：

```
一句话功能
（空行）
Scenario: 场景说明——用户想做什么，工具内部做了什么
（空行）
Args:
    param1: 含义 + 示例值 + 取值约束
    param2: ...
（空行）
Returns:
    返回结构说明
```

要点：
- 描述中**应当**给出前置依赖提示（如 "run list_flavors first"），降低 LLM 试错。
- 参数类型只用 JSON 基本类型（`str/int/float/bool/list/dict`）；枚举值在描述中列全；日期用 ISO 8601；ID 类参数给格式示例。
- 可选参数**必须**有默认值；默认值取向必须安全（最小影响、只读优先）。

RFS `deploy_stack` 的 docstring 是范本（见 `tools/stack.py:101-122`）。

## 3.7 幂等与重试

- WRITE/DANGEROUS 工具**应当**利用 SDK/OpenAPI 的幂等 token（如创建类 API 的 `idempotency` 参数）防止 LLM 重试导致重复创建。
- 工具内部**禁止**自带盲目重试（SDK 已有重试）；长任务**应当**返回任务 ID + 配套查询工具，而不是阻塞等待。如确需等待，提供 `wait` 开关并设超时上限——RFS `deploy_stack` 的 `wait=True, timeout_seconds=300` 就是范例。

## 3.8 风险分级（必须标注每个工具）

| 级别 | 定义 | 示例 |
|---|---|---|
| `READ` | 无资源状态变更 | list、get、analyze、diagnose |
| `WRITE` | 变更可恢复或可再创建的资源 | create、update、stop、restart、resize |
| `DANGEROUS` | 不可逆删除/释放/数据清理，或费用不可撤销 | delete_instance、release_eip、clean_bucket |

每个工具**必须** `@guard(risk=ToolRisk.X)` 声明。未声明的工具会被 middleware 拒绝（`MCP_GUARDRAIL_ERROR`），CI 自检也会失败。

RFS 的风险分布（6 个工具）：

| 工具 | 风险 |
|---|---|
| list_stacks / get_stack / preview_stack_changes / diagnose_stack | READ |
| deploy_stack | WRITE |
| delete_stack | DANGEROUS |

## 3.9 DANGEROUS 工具的 confirm 协议（两段式）

DANGEROUS 工具**必须**定义 `confirm: bool = False` 参数。`confirm=False` 时**不得**执行任何变更，返回预览信息（影响资源清单、`name`/`tags`）与再次调用指引；`confirm=True` 才真正执行。

预览阶段要做两件事：
1. 查资源真实属性（要查详情，本就需要，无额外成本）。
2. 回显 `name` 与 `tags`（人工复核与审计留痕完整）。

RFS `delete_stack` 的 service 实现（`service/stack_service.py:297-351`）是范本：

```python
async def delete_stack(self, *, stack_name, retain_resources=False, confirm=False) -> dict:
    meta = await self._require_stack(stack_name)
    if meta.get("enable_deletion_protection"):
        raise McpToolError(code="MCP_DELETION_PROTECTED", ...)
    if not confirm:
        resources_raw = await self._client.list_stack_resources(stack_name=stack_name)
        ...
        return {
            "confirmation_required": True,
            "preview": {
                "stack_name": stack_name,
                "stack_id": meta.get("stack_id"),
                "status": meta.get("status"),
                "tags": {},                  # 必须回显 tags
                "resource_count": len(resources),
                "resource_types": type_counts,
                "retain_resources": retain_resources,
            },
            "message": "This operation is irreversible...Call again with confirm=true to proceed.",
        }
    # confirm=True：执行不可逆操作前，第二道防线
    assert_not_protected(
        {"id": meta.get("stack_id") or "", "name": stack_name, "tags": {}},
        tool_name="delete_stack",
    )
    await self._client.delete_stack(stack_name=stack_name, retain_all_resources=retain_resources)
    return {"stack_name": stack_name, "deleted": True, ...}
```

注意三层防线在这个工具里全部出现：
1. **middleware 第一层**（参数级匹配，自动）：`stack_name` 在保护名单里直接 block。
2. **service confirm 分支**：`confirm=False` 只返回预览。
3. **service 第二防线**（`assert_not_protected`，强制）：用云上真实属性二次校验，弥补参数级匹配盲区（云上打了保护标签但本次参数没出现该标签的资源）。

## 3.10 装饰器顺序（重要）

```python
@mcp.tool()              # 外层：注册到 MCPServer
@guard(risk=ToolRisk.X)  # 内层：声明风险 + 把 McpToolError 转成错误信封
async def my_tool(...) -> dict:
    ...
```

`@guard` 先执行，把函数包成 "try: return await fn(...) except McpToolError: return exc.to_dict()" 的 wrapper；再由 `@mcp.tool()` 注册这个 wrapper。这样工具内抛的 `McpToolError` 会被转成 `{"error": {...}}` 返回，而不是冒泡到 MCP 框架。

> 反例：如果 `@guard` 在外、`@mcp.tool()` 在内，`@mcp.tool()` 注册的是原始函数（没 catch 异常），工具内抛 `McpToolError` 会冒泡到框架，破坏 LLM 可读性。

## 3.11 工具按资源域分文件

tools 按资源域分文件（`tools/instance.py`、`tools/image.py`），单文件超过 500 行**应当**拆分。RFS 只有 stack 一个资源域，所以只有 `tools/stack.py`。

`tools/__init__.py` 一般为空；注册靠 `server.py` 末尾的 import：

```python
# server.py
mcp = build_server("rfs")
from mcp_server_rfs.tools import stack  # noqa: E402,F401
```

> 必须 `mcp` 赋值之后再 import tools，否则 `@mcp.tool()` 找不到实例（循环导入）。

## 3.12 清单：一个合格的 tools/*.py

- [ ] 每个工具有 `@mcp.tool()` + `@guard(risk=...)`
- [ ] DANGEROUS 工具有 `confirm: bool = False` 参数，且 `confirm=False` 无副作用
- [ ] 每个工具有完整英文 docstring（Scenario / Args / Returns / 前置依赖提示）
- [ ] 工具函数体极薄：只调 service，不写业务逻辑
- [ ] 不直接 import `huaweicloudsdk*`
- [ ] 装饰器顺序正确（`@mcp.tool()` 外、`@guard` 内）
- [ ] 工具数 5–15 个，命名符合动词_对象[_限定]

下一站：[04-service-client.md](04-service-client.md) 讲下两层。
