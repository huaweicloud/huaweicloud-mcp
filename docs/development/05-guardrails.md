# 05 · 安全护栏：分级、保护名单、脱敏、审计

> 源码：`libs/huaweicloud_mcp_core/src/huaweicloud_mcp_core/guardrails/` + `security.py`。

## 5.1 护栏由什么组成

护栏四部分 + 一个串起来的 middleware，全部在核心包，`build_server()` 自动装配，服务**零代码**获得护栏能力：

| 机制 | 位置 | 作用 |
|---|---|---|
| `@guard(risk=...)` 装饰器 | 工具声明处（静态） | 声明风险级并注册到登记表；包装工具把 `McpToolError` 转错误信封 |
| `GuardrailsMiddleware` | MCP 全局中间件 | 每次调用前后：只读检查→声明校验→保护规则→confirm→执行→脱敏→审计 |
| 资源保护名单（rules + protect） | middleware + service 第二防线 | 参数级匹配（middleware）+ 云上真实属性二次校验（service） |
| 输出脱敏（masking） | post-call | 防 AK/SK/密码/token 泄露，不可关闭 |
| 结构化审计（audit） | post-call | JSONL 落盘 + stderr，不可关闭 |

## 5.2 每次工具调用的处理管线

```
tool call (ctx.method == "tools/call")
     │
     ▼
┌─────────────────────────────────────────────────────┐
│     GuardrailsMiddleware（build_server 装配）        │
│                                                     │
│  pre-call:                                          │
│   1. read-only check (WRITE/DANGEROUS)  → block     │
│   2. risk declaration check             → fail-closed│
│   3. protection rules（参数级匹配）                  │
│        action = block / confirm / warn              │
│   4. DANGEROUS confirm=false            → preview   │
│  ────────── execute tool ──────────                 │
│  post-call:                                         │
│   5. masking engine（输出 + 错误统一脱敏）            │
│   6. audit event（JSONL：stderr + 可选文件）          │
└─────────────────────────────────────────────────────┘
```

非 `tools/call` 的请求（如 `tools/list`）直接 `call_next` 透传，不走护栏。

## 5.3 风险分级（必须标注）

| 级别 | 定义 | 示例 |
|---|---|---|
| `READ` | 无资源状态变更 | list、get、analyze、diagnose |
| `WRITE` | 变更可恢复或可再创建的资源 | create、update、stop、restart、resize |
| `DANGEROUS` | 不可逆删除/释放/数据清理，或费用不可撤销 | delete_instance、release_eip、clean_bucket |

每个工具**必须** `@guard(risk=ToolRisk.X)`。`security.py` 把声明写入 `_TOOL_RISK_REGISTRY`，middleware 靠它做声明校验。未声明的工具调用会被 middleware 拒绝（`MCP_GUARDRAIL_ERROR`，message: "Tool 'xxx' has no @guard(risk=...) declaration."）。

## 5.4 规则配置：环境变量 + 可选 YAML

### 简单场景：只用环境变量（无需任何文件）

三个名单变量各自生成一条 `block` 规则：

| 变量 | 说明 | 生成的规则 |
|---|---|---|
| `HUAWEICLOUD_MCP_PROTECTED_IDS` | 逗号分隔的资源 ID（精确匹配） | `ResourceSpec(ids=...)`，action=block |
| `HUAWEICLOUD_MCP_PROTECTED_NAMES` | 逗号分隔的资源名称（精确匹配） | `ResourceSpec(name_patterns=[^name$, ...])`，block |
| `HUAWEICLOUD_MCP_PROTECTED_TAGS` | 逗号分隔标签（`k` 或 `k=v`） | `ResourceSpec(tags=...)`，block |

`load_rules()` 把这三个变量转成 `Rule`，与 YAML 规则并入同一列表。

### 复杂规则：可选 guardrails.yaml

路径由 `HUAWEICLOUD_MCP_GUARDRAILS_CONFIG` 指定：

```yaml
version: 1
rules:
  - id: protect-prod-ecs                  # 必填，全局唯一
    description: 生产 ECS 禁止删除/停机
    match:
      tools: ["delete_*", "stop_*"]       # glob 通配，省略 = 全部
      risks: [DANGEROUS, WRITE]           # 省略 = 全部级别
      resources:
        ids: ["4f0d1c29-..."]             # 精确 ID
        id_prefixes: ["prod-"]            # ID 前缀
        name_patterns: ["^prod-", ".*-prod$"]   # 名称正则
        tags: ["env=prod", "critical"]    # 参数中显式传入的标签
    action: block                         # block | confirm | warn
    message: Production ECS is protected. Contact the ops team.
  - id: staging-needs-confirm
    match:
      risks: [DANGEROUS]
      resources:
        id_prefixes: ["staging-"]
    action: confirm
    message: Staging resources require explicit confirmation.

masking:
  extra_patterns:                         # 追加自定义脱敏（内置集不可关闭）
    - name: corp-internal-key
      regex: 'corpkey-[a-z0-9]{32}'

audit:
  file: /var/log/mcp-audit.jsonl          # 环境变量 HUAWEICLOUD_MCP_AUDIT_FILE 优先
```

### 规则语义（必须）

1. **求值顺序**：按声明顺序对每条规则求值，收集**全部**命中规则。
2. **冲突取严**：多条命中时取最严格动作（`block` > `confirm` > `warn`），`ACTION_ORDER = {"warn":0, "confirm":1, "block":2}`，错误/警告信息列出全部命中规则 ID。
3. **默认放行**：未命中任何规则的调用放行，由分级 + confirm + 只读模式兜底。
4. YAML 在**启动时解析**（fail-fast：格式错、动作非法、ID 重复、正则非法，启动即报错）；运行期规则求值异常走 5.8 fail-closed。

## 5.5 资源保护名单（双层防线）

### 为什么是双层

护栏 middleware 只能看到**工具名与参数值**，因此第一层是**参数级匹配**（零 API 延迟、无额外权限）。但参数级匹配有**已知盲区**：云上打了保护标签、但本次调用参数中未出现该标签的资源，参数级匹配无法命中。

为弥补盲区，设**第二层（service 编排，强制）**：

- 所有 DANGEROUS 工具的 service 编排在执行不可逆操作前，**必须**调用 `assert_not_protected(resource)`，传入从云上查询到的资源**真实**属性（`id`/`name`/`tags`）。
- 命中规则抛 `McpToolError(MCP_GUARDRAIL_BLOCKED)`。
- DANGEROUS 工具的 confirm 预览**必须**回显资源 `name` 与 `tags`（预览数据本就需要查详情，无额外成本），使人工复核与审计留痕完整。

### 第一层：match_arguments（参数级）

`protect.py` 的 `match_arguments(spec, arguments)` 遍历参数值做匹配：
- ID 精确匹配 + ID 前缀匹配
- **`name` 类参数**正则匹配（参数键含 `name`，不区分大小写）
- **`tag` 类参数**：参数键含 `tag`，调 `extract_tag_set` 规范化后匹配

```python
def match_arguments(spec, arguments) -> str | None:
    for key, value in arguments.items():
        for field_key, text in _iter_strings(key, value):
            if text in spec.ids:
                return "id"
            for prefix in spec.id_prefixes:
                if text.startswith(prefix):
                    return f"prefix:{prefix}"
            if "name" in field_key.lower():
                for pattern in spec.regexes:
                    if pattern.search(text):
                        return f"name:{pattern.pattern}"
    for key, value in arguments.items():
        if "tag" in key.lower():
            hit = match_resource(spec, tags=extract_tag_set(value))
            if hit:
                return hit
        ...
    return None
```

返回的 `matched_via` 字符串会进审计日志。

### 第二层：assert_not_protected（强制）

```python
def assert_not_protected(resource: dict, rules=None, tool_name="") -> None:
    rules = rules if rules is not None else load_rules()
    tags = extract_tag_set(resource.get("tags") or {})
    for rule in rules:
        if rule.tools and tool_name and not any(fnmatch.fnmatchcase(tool_name, p) for p in rule.tools):
            continue
        hit = match_resource(
            rule.resources,
            resource_id=str(resource.get("id") or "") or None,
            name=str(resource.get("name") or "") or None,
            tags=tags or None,
        )
        if hit:
            raise McpToolError(
                code="MCP_GUARDRAIL_BLOCKED",
                message=rule.message or f"Resource matches protection rule '{rule.id}' ({hit}).",
                hint=f"Request an exemption for rule '{rule.id}' or remove the resource from the protection list.",
            )
```

RFS `delete_stack` 的调用（`service/stack_service.py:339-342`）：

```python
assert_not_protected(
    {"id": meta.get("stack_id") or "", "name": stack_name, "tags": {}},
    tool_name="delete_stack",
)
```

> 注意：RFS 的 stack 没有云上 tags，所以传 `{}`。VPC/ECS 等有 tags 的服务，要从云上查询结果里取真实 tags 传进去——这正是第二防线弥补盲区的关键。

### 服务 README 必须声明盲区

保护名单是参数级匹配，**有盲区**（云上打了保护标签但本次参数没出现该标签）。服务 README **必须**声明这点并给出配置示例（spec §7.9 强制）。

## 5.6 输出脱敏引擎（不可关闭）

### 内置 pattern 集（对所有出口生效）

| 类别 | 识别规则 | 处理 |
|---|---|---|
| 华为云 AK | 16 位大写字母数字格式 | 值→`***` |
| 华为云 SK | 40 位字母数字格式 | 值→`***` |
| 密码类字段 | 键名含 `password`/`secret`/`token`/`key`/`passwd`/`private_key`/`auth`（不区分大小写，子串） | 值→`***`，追加 `<key>_masked: true` |
| PEM 私钥块 | `-----BEGIN ... PRIVATE KEY-----` 整块 | 整块→`***` |
| Bearer 凭证 | `Bearer xxx` 形态 | 值→`***` |

- 自定义扩展：YAML `masking.extra_patterns` 追加企业内部凭证格式；**内置集不可关闭、不可覆盖**。
- 保守策略：宁可误杀，不可漏放。
- 脱敏发生在 post-call，对返回信封内的 JSON 递归处理；`MaskingEngine.mask(value)` 递归 dict/list/str。

### 对哪些出口生效

- 工具正常输出（dict）
- 错误 JSON 信封（middleware 的 `_error_result` 也过脱敏）
- 审计日志参数摘要（`audit.emit` 先 `_trim_params` 再脱敏）
- `CallToolResult.structured_content`（mcp 2.x 客户端按 output schema 校验）

## 5.7 结构化审计（默认开启、不可关闭）

审计**必须**默认开启；可配置输出位置，**不可**关闭记录本身。事件格式 JSONL：

```json
{
  "ts": "2026-09-20T12:00:00.123Z",
  "event": "tool_call",
  "tool": "delete_stack",
  "risk": "DANGEROUS",
  "decision": "blocked",
  "rules_hit": ["protect-prod-ecs"],
  "action_taken": "block",
  "params": { "stack_name": "prod-web" },
  "request_id": null,
  "duration_ms": 3,
  "error_code": "MCP_GUARDRAIL_BLOCKED"
}
```

- `decision` 取值：`allowed` / `warned` / `confirm_required` / `blocked` / `fail_closed`。
- `params` 经 `_trim_params`（单值 > 200 字符截断）+ 脱敏后落盘；凭证**永不**落盘。
- 输出双通道：stderr（始终）+ 文件（`HUAWEICLOUD_MCP_AUDIT_FILE` 或 YAML `audit.file`，按行追加，轮转由进程外日志方案负责）。

## 5.8 动作三级语义

| 动作 | 行为 | 返回 |
|---|---|---|
| `block` | 拒绝执行 | 统一错误 JSON：`code=MCP_GUARDRAIL_BLOCKED`，含命中规则 ID、规则 message、hint |
| `confirm` | 升级为需确认 | 返回 `confirmation_required=true` 信封，要求 `confirm=true` 重调 |
| `warn` | 放行但告警 | 正常输出 + 顶层附加 `"warnings": [{"rule_id": "...", "message": "..."}]` |

- `confirm` 升级**仅在工具声明了 `confirm` 参数时生效**（`tool_supports_confirm(tool_name)`）；工具无该参数时自动按 `block` 处理，错误信息说明原因。
- 预计会被 `confirm` 规则覆盖的工具（如 `stop_*`）**应当**声明 `confirm` 参数以获得完整两段式体验。
- 拦截类结果**必须**同时填充 text content（JSON）与 `structured_content`（dict）——mcp 2.x 客户端会按工具 output schema 校验结构化输出，缺失会导致客户端报错。

### confirm 动作的预览信封（middleware 生成）

```python
def _confirm_result(self, hits) -> CallToolResult:
    strictest = strictest_hit(hits)
    message = strictest.rule.message if strictest else "Confirmation required."
    payload = {
        "confirmation_required": True,
        "rules_hit": [hit.rule.id for hit in hits],
        "message": f"{message} Call again with confirm=true to proceed.",
    }
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structured_content=payload,
        is_error=False,
    )
```

## 5.9 默认姿态与失效策略

### 开箱默认
保护名单为空（用户显式配置）；以下能力始终生效、不可关闭——风险声明校验、DANGEROUS confirm、只读模式、输出脱敏、结构化审计。

### fail-closed（仅写操作）
护栏引擎运行期异常（规则求值报错、正则错误等）时：
- `READ` 工具：放行，审计记录 `decision=fail_closed`；
- `WRITE` / `DANGEROUS` 工具：拒绝，`code=MCP_GUARDRAIL_ERROR`，hint 指引修复配置。

middleware 的实现（`middleware.py:70-84`）：
```python
except Exception as exc:
    decision = "fail_closed"
    if risk is ToolRisk.READ:
        pre = None                  # 放行
    else:
        error = McpToolError(code="MCP_GUARDRAIL_ERROR",
            message=f"Guardrail engine error while evaluating tool '{tool_name}': {exc}",
            hint="Fix the guardrails configuration (HUAWEICLOUD_MCP_GUARDRAILS_CONFIG).")
        ...
```

### 只读模式
`HUAWEICLOUD_MCP_READ_ONLY=true` 时拦截所有 WRITE/DANGEROUS 调用，返回 `code=MCP_READ_ONLY` 错误（含工具名与级别）。这是 pre-check 的第一步。

## 5.10 强制机制汇总（各服务义务）

1. 每个工具**必须** `@guard(risk=ToolRisk.X)`；未声明的工具被 middleware 拒绝且 CI 检查失败。
2. `DANGEROUS` 工具**必须**定义 `confirm: bool = False` 参数；`confirm=False` 时**不得**执行任何变更，返回预览信息（影响资源清单、`name`/`tags`）与再次调用指引。
3. 只读模式：`HUAWEICLOUD_MCP_READ_ONLY=true` 时拦截所有 WRITE/DANGEROUS 调用。
4. 任何工具**禁止**"批量全选"式删除（如不指定 ID 删全部）；批量操作**必须**显式传入资源 ID 列表且数量上限 ≤ 100。
5. 认证信息**禁止**出现在工具参数中（凭证只来自环境变量）；输出侧泄露由脱敏引擎兜底。
6. DANGEROUS 编排执行不可逆操作前**必须**调用 `assert_not_protected`（第二道防线）。
7. 服务 README **必须**声明保护名单的参数级匹配盲区，并给出配置示例。

### 禁止绕过
服务**不得** catch/吞掉护栏异常后继续执行；**不得**卸载、替换或重排 `GuardrailsMiddleware`；CI 检查 `build_server` 调用链未被篡改。

## 5.11 护栏在测试中怎么覆盖

spec §11.3 要求三类规则动作各有命中测试（middleware 或 service 层）。RFS 的测试样例（`tests/test_service.py:282-292`）：

```python
async def test_delete_blocked_by_protection_rule(service, fake_client, monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_NAMES", "prod-web")
    register_stack(fake_client, "prod-web")
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_stack(stack_name="prod-web", confirm=True)
    assert excinfo.value.code == "MCP_GUARDRAIL_BLOCKED"
    assert all(call[0] != "delete_stack" for call in fake_client.calls)   # 真删除没发生
```

详见 [07-testing.md](07-testing.md)。

下一站：[06-output-errors.md](06-output-errors.md) 讲输出信封与错误 JSON 的细节。
