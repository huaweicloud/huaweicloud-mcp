# 06 · 输出与错误处理规范

> 源码：`libs/huaweicloud_mcp_core/src/huaweicloud_mcp_core/output.py` + `errors.py`。

## 6.1 成功输出（必须结构化 JSON）

工具一律返回结构化 JSON（dict/list），**禁止**返回自然语言大段文本或 Markdown 报告。

### 列表：page_result 信封

```json
{
  "items": [ { "...": "字段白名单裁剪后的对象" } ],
  "count": 20,
  "total": 137,
  "marker": "下一页标记，无更多时为 null",
  "truncated": false
}
```

字段含义：
| 字段 | 含义 |
|---|---|
| `items` | 字段白名单裁剪后的对象数组 |
| `count` | 本次返回条数（= `len(items)`） |
| `total` | 总数；`None` 时取 `len(items)`（SDK 不返回总数时用） |
| `marker` | 下一页标记；无更多时为 `null` |
| `truncated` | `total is not None and total > len(items)`；`total=None` 时恒 `false` |

### 单对象：single_result 信封

直接返回裁剪后的对象，外加可选 `hints`（后续操作建议）：

```json
{
  "stack_id": "...",
  "stack_name": "web",
  "status": "DEPLOYMENT_COMPLETE",
  "outputs": { "eip": "1.2.3.4" },
  "hints": ["Inspect outputs with get_stack."]
}
```

> `single_result` 不再加外层包装——直接在裁剪后的 dict 上加 `hints`。这样 LLM 拿到的就是扁平对象，可读性好。

## 6.2 token 预算（必须）

| 项 | 规则 | 实现 |
|---|---|---|
| 列表默认条数 | 20，`limit` 参数可调，硬上限 100 | `clamp_limit(limit)` = `min(max(limit,1),100)`；`DEFAULT_PAGE_SIZE=20`、`MAX_PAGE_SIZE=100` |
| 字段白名单 | service 层按"LLM 有用"裁剪字段，未列入白名单的丢弃 | `_pick(source, _XXX_FIELDS)` 在 service 层 |
| 长字符串截断 | 单字段 > 2000 字符截断，追加 `_truncated: true` 标记 | `_truncate_value` 递归处理，`MAX_FIELD_LENGTH=2000` |
| 二进制/内联内容 | 禁止内联返回（图片、日志原文），返回引用（URL / OBS 路径 / 资源 ID） | 业务约定 |

### _truncate_value 的截断行为

```python
def _truncate_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > MAX_FIELD_LENGTH:           # 2000
            return value[:MAX_FIELD_LENGTH]           # 截断，不打标记
        return value
    if isinstance(value, (list, tuple)):
        return [_truncate_value(item) for item in value]
    if isinstance(value, dict):
        result = {}
        truncated = False
        for key, item in value.items():
            trimmed = _truncate_value(item)
            if isinstance(item, str) and isinstance(trimmed, str) and len(trimmed) < len(item):
                truncated = True                      # 检测到截断
            result[key] = trimmed
        if truncated:
            result["_truncated"] = True               # 在 dict 层打标记
        return result
    return value
```

注意：截断标记 `_truncated` 打在**包含被截断字段的 dict 层**，不是被截断的字符串本身（字符串无法承载额外字段）。`page_result` 对每个 item 调 `_truncate_value`。

### page_result 内部

```python
def page_result(items, total=None, marker=None) -> dict:
    return {
        "items": [_truncate_value(item) for item in items],
        "count": len(items),
        "total": total if total is not None else len(items),
        "marker": marker,
        "truncated": total is not None and total > len(items),
    }
```

## 6.3 错误输出（必须统一 JSON）

工具内所有异常由核心包统一转换为如下 JSON（**不抛裸异常给 MCP 框架**，保证 LLM 可读）：

```json
{
  "error": {
    "code": "Ecs.0003",
    "message": "The instance ... is not in a valid state for this operation.",
    "request_id": "6b8f1c0f...",
    "doc_url": "https://support.huaweicloud.com/api-ecs/ecs_02_0001.html",
    "hint": "Check instance status via get_instance, then retry after it is ACTIVE."
  }
}
```

### 字段规则

| 字段 | 规则 |
|---|---|
| `code` | 透传华为云 `error_code`；无原生错误码时用内部码（见下表） |
| `message` | 错误描述（人类可读） |
| `request_id` | 有则必须透传（用户提工单的关键凭据）；无则省略 |
| `doc_url` | 可选，官方文档链接 |
| `hint` | **必须**给 LLM 可执行的下一步建议；未提供时 core 兜底 "Inspect the error message and adjust the tool call." |

### 内部错误码（无原生错误码时用）

| 码 | 含义 |
|---|---|
| `MCP_INVALID_ARGS` | 参数校验失败 |
| `MCP_NOT_FOUND` | 资源不存在 |
| `MCP_PERMISSION_DENIED` | 权限不足 |
| `MCP_READ_ONLY` | 只读模式拦截写操作 |
| `MCP_GUARDRAIL_BLOCKED` | 护栏规则拦截 |
| `MCP_GUARDRAIL_ERROR` | 护栏引擎异常 |
| `MCP_SDK_ERROR` | SDK 异常兜底 |
| `MCP_PROJECT_NOT_FOUND` | project_id 解析失败 |

> 服务可自定义 `code`（RFS 用了 `MCP_INVALID_STATE`、`MCP_DELETION_PROTECTED`、`MCP_TIMEOUT`、`MCP_EXECUTION_PLAN_FAILED`），不必非用上面这些。

## 6.4 异常如何变成错误 JSON（两条路径）

### 路径一：@guard 装饰器（工具内抛 McpToolError）

`@guard` 包装函数 `try: return await fn(...) except McpToolError: return exc.to_dict()`。工具内抛的 `McpToolError` 直接被转成 `{"error": {...}}` 返回，不冒泡到框架。

```python
def to_dict(self) -> dict:
    error = {"code": self.code, "message": self.message}
    if self.request_id:
        error["request_id"] = self.request_id
    if self.doc_url:
        error["doc_url"] = self.doc_url
    error["hint"] = self.hint or "Inspect the error message and adjust the tool call."
    return {"error": error}
```

### 路径二：GuardrailsMiddleware（任何异常兜底）

middleware 的 `__call__` 包裹 `call_next`，catch 两类异常：
- `McpToolError` → `decision="blocked"`，`_error_result(exc)`（也过脱敏）
- 其它 `Exception` → 包成 `McpToolError("MCP_SDK_ERROR", str(exc))`，`_error_result`

`_error_result` 生成 `CallToolResult`，content 是 text JSON、structured_content 是 dict（mcp 2.x 客户端按 output schema 校验）：

```python
def _error_result(self, error) -> CallToolResult:
    payload = error.to_dict()
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structured_content=payload,
        is_error=False,
    )
```

> `is_error=False`：mcp 2.x 中 `is_error` 表示"协议层错误"（如参数解析失败），业务错误用结构化 content 表达。所以业务错误设 `is_error=False`，把错误信息放在 content/structured_content 里。

## 6.5 SDK 异常转换（wrap_sdk_error）

```python
def wrap_sdk_error(exc) -> McpToolError:
    ServiceResponseException  → code = error_code or f"HTTP_{status_code}"
                               message = error_msg
                               request_id = request_id
    ClientRequestException    → code = f"HTTP_{status_code}"
    其它                       → code = "MCP_SDK_ERROR"，message = str(exc)
```

华为云 OpenAPI 错误响应带 `error_code` / `error_msg` / `X-Request-Id` 头，`wrap_sdk_error` 全部透传。`request_id` 是用户提工单的关键信息。

### client 层的 404 → None 模式

不是所有异常都要抛。查询类 API 的 404 **应当**在 client 层映射为 `None`，由 service 层决定怎么处理：

```python
try:
    response = self._client.get_stack_metadata(request)
except ServiceResponseException as exc:
    if exc.status_code == 404:
        return None            # 不抛，返回 None
    raise wrap_sdk_error(exc) from exc   # 其它 → McpToolError
```

service 层拿到 `None` 后，要么抛 `MCP_NOT_FOUND`（`_require_stack` 模式），要么当"不存在"处理（如 `deploy_stack` 的"不存在就创建"分支）。

## 6.6 实战：一个完整的错误处理链

以 RFS `get_stack("ghost")` 为例（栈不存在）：

```
tools/get_stack("ghost")
  └→ @guard 包装：try: StackService().get_stack(...) except McpToolError: return to_dict
       └→ service.get_stack
            └→ _require_stack("ghost")
                 └→ client.get_stack_metadata("ghost")
                      └→ SDK 抛 ServiceResponseException(404)
                      └→ client catch 404 → return None
                 └→ meta is None → raise McpToolError(
                        code="MCP_NOT_FOUND",
                        message="Stack 'ghost' not found.",
                        hint="Run list_stacks to see existing stacks in this region.")
       └→ @guard catch McpToolError → return {"error": {code, message, hint}}
  └→ middleware post-call：脱敏（无敏感值）→ 审计 → 返回
```

LLM 最终拿到：

```json
{
  "error": {
    "code": "MCP_NOT_FOUND",
    "message": "Stack 'ghost' not found.",
    "hint": "Run list_stacks to see existing stacks in this region."
  }
}
```

`hint` 告诉 LLM 下一步该调哪个工具——这正是错误信封的设计目标：**错误本身可被 LLM 理解并续接**。

## 6.7 清单：合格的输出与错误处理

- [ ] 所有工具返回 dict/list，无自然语言大段文本
- [ ] 列表用 `page_result`，单对象用 `single_result`
- [ ] limit 经 `clamp_limit` 钳制 1..100
- [ ] service 层有字段白名单 `_pick` + `_XXX_FIELDS`
- [ ] 错误统一 JSON（code/message/request_id?/doc_url?/hint），无裸异常
- [ ] client 层 404→None，其它异常 `wrap_sdk_error`
- [ ] hint 必给可执行下一步

下一站：[07-testing.md](07-testing.md) 讲三层测试怎么写。
