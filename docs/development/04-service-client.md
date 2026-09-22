# 04 · service 与 client 层：编排与 SDK 封装

> 参考实现：`server/mcp_server_rfs/src/mcp_server_rfs/{service,client}/`。

## 4.1 三层依赖回顾

```
tools/    →  service/  →  client/
（注册+guard+docstring）（编排+裁剪+confirm+第二防线）（SDK 封装+异常映射）
```

层间依赖**单向**：tools 可 import service，service 可 import client，client 不感知上面两层。禁止：
- tools 直接 import `huaweicloudsdk*`
- service 直接构建 SDK Client（应注入）
- service 感知 MCP 框架（不 import `mcp` 包）
- client 写业务逻辑或改返回结构

## 4.2 client/ 层 — SDK 封装

### 职责（只做四件事）

1. 构建 SDK Client（凭证、region、endpoint、HttpConfig 超时）——走核心包。
2. 薄封装每个用到的 API：函数签名**应当**与 OpenAPI action 一一对应并保留原名（如 `list_servers_details`），便于追溯与测试。
3. 异常透传：404→None（可选）、其它→`wrap_sdk_error(exc)`。
4. SDK response 对象 → 纯 dict（`sdk_to_dict`），本层无业务逻辑。

### 构造函数：双入口（生产 + 测试）

```python
class RfsClient:
    def __init__(self, settings: McpSettings | None = None, sdk_client: Any = None) -> None:
        self._settings = settings or McpSettings.from_env()
        if sdk_client is not None:
            self._client = sdk_client          # 测试注入 fake
        else:
            self._client = (
                _SdkRfsClient.new_builder()
                .with_credentials(build_credentials(CredentialScope.PROJECT, self._settings))
                .with_region(RfsRegion.value_of(self._settings.region))
                .build()
            )
```

`sdk_client` 参数是测试注入点——client 层测试注入 `RecordingSdkClient`，service 层测试注入 `FakeRfsClient`。这两个注入点形态不同：
- client 层测试注入的是**假 SDK Client**（实现 SDK 的方法名，如 `list_stacks(request)`）。
- service 层测试注入的是**假 client**（实现 client 的 async 方法名，如 `await list_stacks(...)`）。

详见 [07-testing.md](07-testing.md)。

### 同步 SDK + async 工具的桥接（重要）

huaweicloudsdk 是**同步**客户端，MCP 工具是 async。直接 `await self._client.list_stacks(request)` 会阻塞事件循环，streamable-http 模式下并发会饿死。**应当**用 `asyncio.to_thread` 包装：

```python
async def list_stacks(self, *, limit: int, marker: str | None) -> dict[str, Any]:
    def _call() -> dict[str, Any]:
        request = ListStacksRequest(limit=limit, marker=marker)
        return sdk_to_dict(self._client.list_stacks(request))
    return await asyncio.to_thread(_call)
```

每个方法都用这个 `_call` 内部函数 + `asyncio.to_thread` 的模式。这是 client 层的标准写法，RFS 全部 11 个方法都这么写。

### sdk_to_dict — SDK 响应转纯 dict

SDK 响应是带 `_` 前缀私有属性的对象，不能直接 JSON 序列化。`sdk_to_dict` 递归转换：

```python
_SKIP_ATTRS = {"local_vars_configuration", "discriminator", "swagger_types"}

def sdk_to_dict(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): sdk_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sdk_to_dict(item) for item in obj]
    result: dict[str, Any] = {}
    for key, value in vars(obj).items():
        if key in _SKIP_ATTRS or key.startswith("__") or callable(value):
            continue
        result[key.lstrip("_")] = sdk_to_dict(value)   # 去掉前缀 _
    return result
```

要点：
- 跳过 SDK 内部字段（`local_vars_configuration` 等）。
- `_` 前缀属性去前缀（`_name` → `name`）。
- 递归处理嵌套对象、list、dict。
- 返回纯 dict/list/标量，可被 JSON 序列化。

> 把这个函数放 client 层（如 `rfs_client.py` 顶部），service 层拿到的就是纯 dict 了。

### 404 → None 模式

查询类 API 的 404 **应当**映射为 `None`，由 service 层决定怎么处理（抛 `MCP_NOT_FOUND` 或当"不存在"处理）。RFS `get_stack_metadata`：

```python
async def get_stack_metadata(self, stack_name: str) -> dict[str, Any] | None:
    def _call():
        request = GetStackMetadataRequest(stack_name=stack_name)
        try:
            response = self._client.get_stack_metadata(request)
        except ServiceResponseException as exc:
            if exc.status_code == 404:
                return None
            raise wrap_sdk_error(exc) from exc
        return sdk_to_dict(response)
    return await asyncio.to_thread(_call)
```

注意返回类型是 `dict | None`，不是 `dict`。

### SDK 模型对象的组装

client 层负责把 dict 参数组装成 SDK 的 Request/Body 对象。RFS 的 `_vars_structure` 是范例：

```python
def _vars_structure(variables: dict[str, str] | None) -> list[VarsStructure]:
    return [
        VarsStructure(var_key=str(key), var_value=str(value))
        for key, value in (variables or {}).items()
    ]
```

然后在 `create_stack` 里：
```python
body = CreateStackRequestBody(
    stack_name=stack_name,
    template_body=template_body,
    template_uri=template_uri,
    vars_structure=_vars_structure(variables),
    enable_deletion_protection=enable_deletion_protection,
    description=description,
)
request = CreateStackRequest(body=body)
return sdk_to_dict(self._client.create_stack(request))
```

> client 层不校验业务（如"template 和 template_uri 不能同时给"），那是 service 层的事。

## 4.3 service/ 层 — 编排

### 职责（六件事）

1. 业务逻辑：组合多个 client 调用、校验、等待、回填。
2. 分页钳制：`limit = clamp_limit(limit)`，把 limit 钳在 1..100。
3. 字段白名单裁剪：按"LLM 有用"裁剪字段，未列入白名单的丢弃。
4. 组装信封：列表用 `page_result`，单对象用 `single_result`。
5. confirm 分支：DANGEROUS 工具的 `confirm=False` 返回预览。
6. 护栏第二防线：执行不可逆操作前 `assert_not_protected`。

### 构造函数：注入 client

```python
class StackService:
    def __init__(self, client: RfsClient | None = None) -> None:
        self._client = client or RfsClient()
```

`client` 参数是 service 层测试注入点。生产用默认 `RfsClient()`，测试注入 `FakeRfsClient`。

### 字段白名单（service 层定义，不是核心包）

```python
_STACK_FIELDS = (
    "stack_id", "stack_name", "status", "status_message",
    "description", "create_time", "update_time", "enable_deletion_protection",
)

def _pick(source: dict, fields: tuple[str, ...]) -> dict:
    return {key: source[key] for key in fields if source.get(key) is not None}
```

`_pick` 是 service 层通用辅助函数：从 SDK 转来的 dict 里只取白名单字段、跳过 None。每个资源域定义自己的白名单元组。

> 为什么白名单在 service 不在 core？因为"哪些字段对 LLM 有用"是业务判断，各服务不同；core 只负责信封外壳和截断。

### 分页查询范式

```python
async def list_stacks(self, *, name=None, limit=20, marker=None) -> dict:
    limit = clamp_limit(limit)                       # 1..100
    response = await self._client.list_stacks(limit=limit, marker=marker)
    stacks = [_pick(s, _STACK_FIELDS) for s in response.get("stacks") or []]
    if name:                                          # 内存过滤（SDK 不支持时）
        stacks = [s for s in stacks if name.lower() in str(s.get("stack_name","")).lower()]
    next_marker = (response.get("page_info") or {}).get("next_marker")
    return page_result(stacks, total=None, marker=next_marker)
```

要点：
- `clamp_limit` 必调（防 LLM 传 99999）。
- SDK 不支持的过滤条件，在 service 层内存过滤（如按 name 子串）。
- `total=None` 当 SDK 不返回总数（RFS list API 就不返回）；`total=明确数` 当 SDK 返回。
- `marker` 取 SDK 返回的下一页标记，无更多时为 `None`。

### 单对象 + 派生数据范式

`get_stack` 范式：查元数据 + 查 outputs，组装成单个对象返回。

```python
async def get_stack(self, *, stack_name: str) -> dict:
    meta = await self._require_stack(stack_name)
    outputs_raw = await self._client.list_stack_outputs(stack_name=stack_name)
    outputs = outputs_raw.get("outputs") or outputs_raw.get("stack_outputs") or []
    output_map = {
        str(item.get("output_key")): item.get("output_value")
        for item in outputs if isinstance(item, dict)
    }
    payload = _pick(meta, _STACK_FIELDS)
    payload["outputs"] = output_map
    return single_result(payload)
```

> 注意 SDK 返回的 key 可能是 `outputs` 也可能是 `stack_outputs`（不同 API 命名不一），service 层做兼容。

### "不存在"的处理

```python
async def _require_stack(self, stack_name: str) -> dict:
    meta = await self._client.get_stack_metadata(stack_name)
    if meta is None:                       # client 层把 404 转成了 None
        raise McpToolError(
            code="MCP_NOT_FOUND",
            message=f"Stack '{stack_name}' not found.",
            hint="Run list_stacks to see existing stacks in this region.",
        )
    return meta
```

`_require_stack` 是"要求存在，不存在就抛"的通用辅助。各 service 都会有类似的 `_require_xxx`。

### 编排多 API + 等待（deploy_stack 范例）

`deploy_stack` 是最复杂的编排范例，演示了：查存在性 → 分支创建/更新 → 可选等待 → 回填 outputs。

```python
async def deploy_stack(self, *, stack_name, template=None, template_uri=None,
                       variables=None, enable_deletion_protection=False,
                       wait=False, timeout_seconds=300) -> dict:
    _validate_template_args(template, template_uri)   # 业务校验
    meta = await self._client.get_stack_metadata(stack_name)
    if meta is None:                                    # 不存在 → 创建
        await self._client.create_stack(...)
        action = "created"
        deployment = {}
    else:                                               # 存在 → 更新
        status = str(meta.get("status") or "")
        if status in _IN_PROGRESS:                     # 并发保护
            raise McpToolError(code="MCP_INVALID_STATE", ...)
        deployment = await self._client.deploy_stack(...)
        action = "updated"
    result = {"stack_name": stack_name, "action": action, "status": None, "deployment_id": ...}
    if wait:                                            # 可选等待
        meta = await self._wait_terminal(stack_name, timeout_seconds)
        result["waited"] = True
        result["status"] = meta.get("status")
        if str(meta.get("status")) in _COMPLETE:
            result["outputs"] = await self._fetch_outputs(stack_name)
    result["hints"] = ["Track progress with get_stack or diagnose_stack."]
    if str(result.get("status")) in _FAILED:
        result["hints"].append("Deployment failed; run diagnose_stack...")
    return result
```

要点：
- 业务校验在 service（`_validate_template_args`），不在 client 也不在 tools。
- 并发保护：状态在 `_IN_PROGRESS` 时拒绝，抛 `MCP_INVALID_STATE`。
- `wait` 开关 + 超时上限，不盲目阻塞。
- `hints` 给 LLM 可执行的下一步。

### 诊断/分析类工具（diagnose_stack 范例）

诊断类工具是"有附加值的场景工具"的最佳示例——它把多个查询 API 的结果**聚合 + 推理**：

```python
async def diagnose_stack(self, *, stack_name, event_limit=20) -> dict:
    meta = await self._require_stack(stack_name)
    events_raw = await self._client.list_stack_events(stack_name=stack_name, limit=clamp_limit(event_limit))
    resources_raw = await self._client.list_stack_resources(stack_name=stack_name)
    events = [_pick(e, _EVENT_FIELDS) for e in events_raw.get("stack_events") or []]
    events.sort(key=lambda e: str(e.get("event_time") or ""), reverse=True)   # 最新在前
    resources = [_pick(r, _RESOURCE_FIELDS) for r in resources_raw.get("stack_resources") or []]
    failed_events = [e for e in events if "FAIL" in str(e.get("status") or "")]
    failed_resources = [r for r in resources if "FAIL" in str(r.get("status") or "")]
    status = str(meta.get("status") or "")
    analysis = []                                       # 推理结论
    if status in _IN_PROGRESS:
        analysis.append("An operation is in progress; failures may be transient.")
    if failed_events:
        latest = failed_events[0]
        analysis.append(f"Most recent failure: resource '{latest.get('resource_name')}'...")
    ...
    hints = [...]                                       # 下一步建议
    return {
        "stack": _pick(meta, _STACK_FIELDS),
        "recent_failed_events": failed_events[:10],
        "failed_resources": failed_resources,
        "analysis": analysis,
        "hints": hints,
    }
```

> `analysis` 和 `hints` 是诊断类工具的标志——它们不只返回原始数据，还给出推理结论和行动建议。这类工具天然只读、安全，应优先设计。

### 轮询等待范式

```python
async def _wait_terminal(self, stack_name, timeout_seconds) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while True:
        meta = await self._client.get_stack_metadata(stack_name)
        if meta is None:
            raise McpToolError(code="MCP_NOT_FOUND", message="...disappeared while waiting.", ...)
        status = str(meta.get("status") or "")
        if status in _FAILED or status in _COMPLETE:
            return meta
        if time.monotonic() >= deadline:
            return meta                  # 超时返回当前状态，不抛
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
```

要点：
- 用 `time.monotonic()` 算 deadline（不受系统时钟影响）。
- 终态（`_FAILED` / `_COMPLETE`）返回；超时返回当前状态（不抛，让上层决定）。
- 资源消失抛 `MCP_NOT_FOUND`。
- `_POLL_INTERVAL_SECONDS` 是模块级常量，测试用 `monkeypatch.setattr(..., "_POLL_INTERVAL_SECONDS", 0)` 跳过等待。

## 4.4 清单：一个合格的 service/client 对

**client/*.py**
- [ ] 薄封装，函数名与 OpenAPI action 对应
- [ ] 构造函数有 `sdk_client` 注入参数
- [ ] 异常透传（404→None，其它→`wrap_sdk_error`）
- [ ] `asyncio.to_thread` 包装阻塞调用
- [ ] `sdk_to_dict` 转纯 dict
- [ ] 无业务逻辑、无返回结构修改

**service/*.py**
- [ ] 构造函数有 `client` 注入参数
- [ ] `clamp_limit` 钳制 limit
- [ ] 字段白名单裁剪（`_pick` + `_XXX_FIELDS`）
- [ ] 列表用 `page_result`、单对象用 `single_result`
- [ ] DANGEROUS 工具有 confirm 分支 + `assert_not_protected`
- [ ] 不 import `mcp` 包、不构建 SDK Client
- [ ] 业务校验在此层（不在 client 也不在 tools）

下一站：[05-guardrails.md](05-guardrails.md) 讲护栏五件套的完整机制。
