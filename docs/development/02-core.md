# 02 · 公共核心包 huaweicloud-mcp-core

> 源码位置：`libs/huaweicloud_mcp_core/src/huaweicloud_mcp_core/`。本文档与代码冲突时以源码为准。

## 2.1 它解决什么问题

每个华为云服务的 MCP Server 都要做这些事：读凭证、解析 project_id、调同步 SDK、把异常包成 LLM 可读的 JSON、限制输出条数、做风险分级与保护名单……如果每个服务各写一份，安全/认证逻辑必然分叉。

核心包 `huaweicloud-mcp-core` 把这些**统一收口**，对外提供稳定的导入接口：

```python
from huaweicloud_mcp_core import (
    McpSettings,          # 配置
    CredentialScope,      # 凭证作用域
    build_credentials,    # 构建 SDK 凭证
    McpToolError,         # 唯一允许的业务异常
    wrap_sdk_error,       # SDK 异常 → McpToolError
    page_result,          # 分页信封
    single_result,        # 单对象信封
    ToolRisk,             # 风险分级
    guard,                # @guard 装饰器
    build_server,         # 构造 MCPServer（自动装护栏）
    run_standard,         # 统一入口/传输选择
)
from huaweicloud_mcp_core.guardrails import assert_not_protected, load_rules
```

**硬性约束**：服务**禁止**自行实现认证、project_id 解析、错误封装、只读拦截、脱敏、审计——一律从核心包 import 后使用（允许扩展，不允许重写）。

## 2.2 模块地图

```
huaweicloud_mcp_core/
├── __init__.py     # 顶层 re-export（上面的导入就来自这里）
├── config.py       # 环境变量 → 不可变 McpSettings
├── credentials.py  # build_credentials + project_id 自动解析（带缓存）
├── errors.py       # McpToolError + wrap_sdk_error
├── security.py     # ToolRisk + @guard 装饰器 + 风险登记表
├── output.py       # page_result / single_result / clamp_limit / 截断
├── server.py       # build_server / run_standard
└── guardrails/
    ├── __init__.py
    ├── rules.py       # Rule/ResourceSpec 模型 + 加载/求值
    ├── protect.py    # 参数级匹配 + assert_not_protected 第二防线
    ├── masking.py     # 脱敏引擎（不可关闭）
    ├── audit.py       # 结构化 JSONL 审计
    └── middleware.py  # GuardrailsMiddleware（唯一拦截点）
```

下面逐模块讲**职责、关键签名、用法示例**。示例均与 `server/mcp_server_rfs/` 真实代码对齐。

---

## 2.3 config.py — 配置的唯一入口

### 职责
- 从环境变量读取全部配置，生成**不可变**的 `McpSettings`（`@dataclass(frozen=True)`）。
- 缺失必需变量时抛带修复指引的 `McpToolError`（提示 export 哪个变量）。
- 服务**不得**直接 `os.getenv` 读认证类变量；自定义业务变量可以自行读，但必须以 `HUAWEICLOUD_MCP_<SERVICE>_` 为前缀。

### 关键签名

```python
@dataclass(frozen=True)
class McpSettings:
    access_key: str = ""
    secret_key: str = ""
    region: str = ""
    project_id: str | None = None
    security_token: str | None = None
    endpoint: str | None = None
    read_only: bool = False
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    protected_ids: tuple[str, ...] = ()
    protected_names: tuple[str, ...] = ()
    protected_tags: tuple[str, ...] = ()
    guardrails_config_path: str | None = None
    audit_file: str | None = None

    @classmethod
    def from_env(cls, *, require_credentials: bool = True) -> McpSettings: ...
```

### `require_credentials` 的两副面孔（重要）

| 场景 | 传参 | 行为 |
|---|---|---|
| 工具运行期（要调云 API） | `require_credentials=True`（默认） | 缺 AK/SK/REGION 直接抛错 |
| 启动期构建 server、`--help`、跑测试导入 | `require_credentials=False` | 不校验凭证，延迟到真正调用时才校验 |

这个区分保证了 `uv run mcp_server_rfs --help` 不会因为没配凭证而崩溃，也保证了测试可以 `import` 模块而不触发凭证校验。`build_server()` 内部用的就是 `require_credentials=False`。

### 用法

```python
from huaweicloud_mcp_core.config import McpSettings

# 启动期：不强制凭证
settings = McpSettings.from_env(require_credentials=False)

# 工具运行期：强制（缺失即抛带 hint 的 McpToolError）
settings = McpSettings.from_env()
```

辅助函数 `_env_bool` / `_env_csv` / `_env_int` 是内部实现，服务一般不直接用。读自定义业务变量用标准 `os.getenv`，但前缀必须是 `HUAWEICLOUD_MCP_<SERVICE>_`。

---

## 2.4 credentials.py — 凭证与 project_id

### 职责
- `build_credentials(scope)` 按作用域产出 `BasicCredentials`（项目级）或 `GlobalCredentials`（全局级）。
- `resolve_project_id()` 自动解析 project_id：`HUAWEICLOUD_PROJECT_ID` 环境变量 > IAM `keystone_list_projects`（按 region 名过滤，进程内缓存）。
- STS 临时凭证（`HUAWEICLOUD_SECURITY_TOKEN`）可选附加。
- **禁止**在日志或异常里输出 AK/SK/token 明文。

### 关键签名

```python
class CredentialScope(Enum):
    PROJECT = "project"   # BasicCredentials，ECS/OBS/RDS 等项目级服务
    GLOBAL = "global"     # GlobalCredentials，IAM 等全局服务

def resolve_project_id(settings: McpSettings | None = None) -> str: ...
def build_credentials(
    scope: CredentialScope = CredentialScope.PROJECT,
    settings: McpSettings | None = None,
) -> BasicCredentials | GlobalCredentials: ...
def reset_project_cache() -> None: ...   # 测试间清缓存用
```

### project_id 解析优先级

```
HUAWEICLOUD_PROJECT_ID（显式） → 命中即返回
        ↓ 未设
进程内缓存 _PROJECT_CACHE[region] → 命中即返回
        ↓ 未命中
IAM keystone_list_projects(name=region) → 取 projects[0].id，写缓存
```

IAM 解析失败（权限不足 / 无项目）会抛 `McpToolError`，hint 引导用户去控制台 "My Credentials > Project List" 手动设 `HUAWEICLOUD_PROJECT_ID`。**这是新服务接入最常见的报错**，README 里要写清楚。

### 用法（client 层标准写法）

```python
from huaweicloud_mcp_core.config import McpSettings
from huaweicloud_mcp_core.credentials import CredentialScope, build_credentials
from huaweicloudsdkrfs.v1 import RfsClient as _SdkRfsClient
from huaweicloudsdkrfs.v1.region.rfs_region import RfsRegion

class RfsClient:
    def __init__(self, settings: McpSettings | None = None, sdk_client=None) -> None:
        self._settings = settings or McpSettings.from_env()
        if sdk_client is not None:
            self._client = sdk_client          # 测试注入
        else:
            self._client = (
                _SdkRfsClient.new_builder()
                .with_credentials(build_credentials(CredentialScope.PROJECT, self._settings))
                .with_region(RfsRegion.value_of(self._settings.region))
                .build()
            )
```

> 全局服务（IAM 等）用 `CredentialScope.GLOBAL`，得到的是 `GlobalCredentials`（domain 级，不带 project_id）。client 层必须在 README 标注本服务用哪个 scope。

---

## 2.5 errors.py — 唯一异常与 SDK 异常转换

### 职责
- `McpToolError`：工具层**唯一允许**抛出的业务异常。
- `wrap_sdk_error(exc)`：把 `huaweicloudsdkcore` 的 `ServiceResponseException` / `ClientRequestException` 统一转成 `McpToolError`，保留 `error_code`/`error_msg`/`request_id`。

### 关键签名

```python
class McpToolError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        request_id: str | None = None,
        doc_url: str | None = None,
        hint: str | None = None,
    ) -> None: ...
    def to_dict(self) -> dict: ...   # → {"error": {code,message,request_id?,doc_url?,hint}}

def wrap_sdk_error(exc: Exception) -> McpToolError: ...
```

### 内部错误码集

`_INTERNAL_CODES`（用于无原生错误码时的兜底）：

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

> 服务可以用任意自定义 `code`（如 RFS 用了 `MCP_INVALID_STATE`、`MCP_DELETION_PROTECTED`、`MCP_TIMEOUT`），不必非用上面这些。

### `wrap_sdk_error` 的转换逻辑

```python
ServiceResponseException  → code = error_code or f"HTTP_{status_code}"
                           message = error_msg
                           request_id = request_id
ClientRequestException    → code = f"HTTP_{status_code}"
其它异常                   → code = "MCP_SDK_ERROR"，message = str(exc)
```

### 用法（client 层）

```python
from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException
from huaweicloud_mcp_core.errors import wrap_sdk_error

async def get_stack_metadata(self, stack_name: str) -> dict | None:
    def _call():
        request = GetStackMetadataRequest(stack_name=stack_name)
        try:
            response = self._client.get_stack_metadata(request)
        except ServiceResponseException as exc:
            if exc.status_code == 404:        # 404 → None，不抛
                return None
            raise wrap_sdk_error(exc) from exc   # 其它 → McpToolError
        return sdk_to_dict(response)
    return await asyncio.to_thread(_call)
```

注意：`McpToolError` 不会直接抛给 MCP 框架。`@guard` 装饰器会 catch 它并转成错误信封 dict（见 2.6 与 03-tools）。护栏 middleware 也会 catch 并转信封（见 05-guardrails）。

---

## 2.6 security.py — 风险分级与 @guard

### 职责
- `ToolRisk` 三级枚举：`READ` / `WRITE` / `DANGEROUS`。
- `@guard(risk=...)` 装饰器：声明风险级、注册到全局登记表、把 `McpToolError` 转成错误信封、记录是否带 `confirm` 参数。
- 提供查询函数供 middleware 用。

### 关键签名

```python
class ToolRisk(Enum):
    READ = "READ"
    WRITE = "WRITE"
    DANGEROUS = "DANGEROUS"

def guard(*, risk: ToolRisk) -> Callable[[F], F]: ...

# 查询（middleware / CI 自检用）
def get_tool_risk(tool_name: str) -> ToolRisk | None: ...
def tool_supports_confirm(tool_name: str) -> bool: ...
def reset_registries() -> None: ...   # 测试间清登记表
```

### @guard 做了三件事

1. **注册**：把 `fn.__name__ → risk` 写入模块级 `_TOOL_RISK_REGISTRY`；middleware 靠它判断"工具是否声明了风险级"。
2. **标记 confirm 能力**：若签名含 `confirm` 参数，加入 `_TOOLS_WITH_CONFIRM`；middleware 的 `confirm` 规则升级靠它判断"工具是否支持两段式"。
3. **包装**：`try: return await fn(...) except McpToolError: return exc.to_dict()`——把异常转成 `{"error": {...}}` 信封，**不抛裸异常给 MCP 框架**。

### 用法（tools 层）

```python
from huaweicloud_mcp_core.security import ToolRisk, guard
from mcp_server_rfs.server import mcp

@mcp.tool()
@guard(risk=ToolRisk.DANGEROUS)
async def delete_stack(
    stack_name: str,
    retain_resources: bool = False,
    confirm: bool = False,        # DANGEROUS 工具必须带这个参数
) -> dict:
    """Delete an RFS stack..."""
    return await StackService().delete_stack(
        stack_name=stack_name, retain_resources=retain_resources, confirm=confirm,
    )
```

> 装饰器顺序：`@mcp.tool()` 在外，`@guard(...)` 在内。`@guard` 先把函数包成"catch McpToolError 转 dict"的 wrapper，再由 `@mcp.tool()` 注册。这样工具内抛的 `McpToolError` 会被转成错误信封返回，而不是冒泡到框架。

---

## 2.7 output.py — 输出信封与 token 预算

### 职责
- 列表用 `page_result` 信封；单对象用 `single_result`。
- `clamp_limit(limit)` 把 limit 钳在 1..100。
- `_truncate_value` 递归截断超长字符串（>2000 字符）并打 `_truncated: true` 标记。

### 关键签名与常量

```python
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_FIELD_LENGTH = 2000

def clamp_limit(limit: int) -> int: ...   # min(max(limit,1),100)

def page_result(
    items: list[dict],
    total: int | None = None,
    marker: str | None = None,
) -> dict: ...

def single_result(
    obj: dict,
    hints: list[str] | None = None,
) -> dict: ...
```

### page_result 信封结构

```json
{
  "items": [ ...裁剪后的对象... ],
  "count": 20,
  "total": 137,
  "marker": "下一页标记，无更多时为 null",
  "truncated": true
}
```

`truncated`：`total is not None and total > len(items)`。注意 service 层传 `total=None` 时，`truncated` 恒为 `false`、`total` 等于 `len(items)`——RFS 的 `list_stacks` 就这么用（RFS list API 不返回总数）。

### 用法（service 层）

```python
from huaweicloud_mcp_core.output import clamp_limit, page_result, single_result

async def list_stacks(self, *, name=None, limit=20, marker=None) -> dict:
    limit = clamp_limit(limit)                       # 钳制 1..100
    response = await self._client.list_stacks(limit=limit, marker=marker)
    stacks = [_pick(s, _STACK_FIELDS) for s in response.get("stacks") or []]
    if name:
        stacks = [s for s in stacks if name.lower() in str(s.get("stack_name","")).lower()]
    next_marker = (response.get("page_info") or {}).get("next_marker")
    return page_result(stacks, total=None, marker=next_marker)

async def get_stack(self, *, stack_name) -> dict:
    meta = await self._require_stack(stack_name)
    ...
    return single_result(payload, hints=["Inspect outputs with get_stack."])
```

> 字段白名单裁剪（`_pick` / `_STACK_FIELDS`）是 **service 层**的职责，不是核心包的。核心包只负责信封外壳和截断；"哪些字段对 LLM 有用"由各服务自己定义。

---

## 2.8 server.py — 构建与运行

### 职责
- `build_server(service_name, settings)`：创建 `MCPServer(f"huaweicloud-{service_name}")`，**自动装配** `GuardrailsMiddleware`。服务零代码获得护栏。
- `run_standard(server, service_name)`：统一 argparse（`-t/--transport`），stdio / streamable-http 二选一。

### 关键签名

```python
def build_server(service_name: str, settings: McpSettings | None = None) -> MCPServer: ...
def run_standard(server: MCPServer, service_name: str) -> None: ...
```

### build_server 内部做了什么

```python
def build_server(service_name, settings=None) -> MCPServer:
    resolved = settings or McpSettings.from_env(require_credentials=False)  # 启动期不强制凭证
    rules = load_rules(resolved)            # 加载护栏规则（fail-fast）
    audit = AuditLogger(file_path=resolved.audit_file)
    middleware = GuardrailsMiddleware(read_only=resolved.read_only, rules=rules, audit=audit)
    return MCPServer(f"huaweicloud-{service_name}", middleware=[middleware])
```

关键点：
1. 用 `require_credentials=False`——`--help` 和测试导入不因缺凭证崩。
2. `load_rules` 在这里**启动期**执行，YAML 格式错 / 动作非法 / 规则 ID 重复 / 正则非法会**立即报错**（fail-fast）。
3. middleware 装在 `middleware=[...]`，mcp 2.x 的 `ServerMiddleware` 协议。

### run_standard 的传输选择

```python
def run_standard(server, service_name) -> None:
    parser = argparse.ArgumentParser(...)
    parser.add_argument("--transport", "-t", choices=["stdio","streamable-http"], default="stdio")
    args = parser.parse_args()
    if args.transport == "streamable-http":
        settings = McpSettings.from_env(require_credentials=False)
        server.run(transport="streamable-http", host=settings.server_host, port=settings.server_port)
    else:
        server.run(transport=args.transport)
```

- streamable-http 监听地址由 `MCP_SERVER_HOST`/`MCP_SERVER_PORT` 控制，默认 `0.0.0.0:8000`。
- **stdio 模式下 stdout 必须绝对干净**（见附录 B.1）；日志一律 stderr，核心包 `logging` 默认 `StreamHandler(sys.stderr)`。

### 用法（server.py + main.py 标准写法）

`server.py`：
```python
from huaweicloud_mcp_core.server import build_server

mcp = build_server("rfs")

# import 即注册：tools 包内每个模块都会向该实例注册工具
# 注意：必须在 mcp 赋值之后再 import，避免循环导入
from mcp_server_rfs.tools import stack  # noqa: E402,F401
```

`main.py`：
```python
from mcp_server_rfs.server import mcp
from huaweicloud_mcp_core.server import run_standard

def main() -> None:
    run_standard(mcp, service_name="rfs")

if __name__ == "__main__":
    main()
```

> 服务**禁止**自行实例化 `MCPServer`、**禁止**自行写 argparse、**禁止**卸载/替换 `GuardrailsMiddleware`。CI 自检会查 `build_server` 调用链未被篡改。

---

## 2.9 guardrails/ 子包 — 安全护栏五件套

护栏由四部分组成：**风险分级**（security.py，见 2.6）、**资源保护名单**（protect.py）、**输出脱敏**（masking.py）、**结构化审计**（audit.py），用 `GuardrailsMiddleware`（middleware.py）串起来，`build_server()` 自动装配。详细机制见 [05-guardrails.md](05-guardrails.md)，这里给 API 速查。

### rules.py — 规则模型与求值

```python
VALID_ACTIONS = ("block", "confirm", "warn")
ACTION_ORDER = {"warn": 0, "confirm": 1, "block": 2}   # 冲突取严

@dataclass(frozen=True)
class ResourceSpec:
    ids: tuple[str, ...] = ()
    id_prefixes: tuple[str, ...] = ()
    name_patterns: tuple[str, ...] = ()     # 正则
    tags: tuple[str, ...] = ()               # "k" 或 "k=v"
    def is_empty(self) -> bool: ...
    @property
    def regexes(self) -> tuple[re.Pattern[str], ...]: ...

@dataclass(frozen=True)
class Rule:
    id: str
    action: str
    message: str = ""
    description: str = ""
    tools: tuple[str, ...] = ()              # glob 通配
    risks: tuple[ToolRisk, ...] = ()
    resources: ResourceSpec = ...
    def matches_tool(self, tool_name: str, risk: ToolRisk) -> bool: ...

@dataclass(frozen=True)
class RuleHit:
    rule: Rule
    matched_via: str                         # "id"/"prefix:.."/"name:.."/"tag:.."/"no-resource-filter"

def load_rules(settings: McpSettings | None = None) -> list[Rule]: ...
def evaluate_rules(rules, tool_name, risk, arguments) -> list[RuleHit]: ...  # 返回全部命中
def strictest_hit(hits: list[RuleHit]) -> RuleHit | None: ...               # 取最严
```

- `load_rules` 合并环境变量名单（`PROTECTED_IDS/NAMES/TAGS`）与 YAML，**启动期** `_validate`（动作非法/ID 重复/正则非法即报错）。
- `evaluate_rules` 对每条规则按声明顺序求值，返回**全部**命中；上游 `strictest_hit` 取最严动作。
- `Rule.matches_tool`：`tools` 用 `fnmatch` glob 通配（`delete_*`），`risks` 精确匹配；都省略 = 匹配全部。

### protect.py — 参数级匹配 + 第二防线

```python
def extract_tag_set(value: Any) -> set[str]: ...   # dict/list/'k=v' → {"k=v",...}
def match_resource(spec, *, resource_id=None, name=None, tags=None) -> str | None: ...
def match_arguments(spec: ResourceSpec, arguments: dict) -> str | None: ...  # 参数级
def assert_not_protected(resource: dict, rules=None, tool_name="") -> None: ...
```

- `match_arguments`：参数级匹配（零 API 延迟）。遍历参数值，匹配 ID 精确/前缀、`name` 类参数正则、`tag` 类参数。
- `assert_not_protected`：**第二防线**。DANGEROUS 编排执行不可逆操作前**必须**调用，传入从云上查到的**真实**属性（`id`/`name`/`tags`）；命中规则抛 `McpToolError(MCP_GUARDRAIL_BLOCKED)`。

### masking.py — 脱敏引擎（不可关闭）

```python
MASK = "***"
_FIELD_KEY_MARKERS = ("password","secret","token","passwd","private_key","auth")
_VALUE_PATTERNS = (  # 内置，不可关闭
    16位大写字母数字,        # AK
    40位字母数字,           # SK
    PEM 私钥块,
    Bearer xxx,
)

class MaskingEngine:
    def __init__(self, extra_patterns: tuple[ExtraPattern,...] = ()) -> None: ...
    def mask_text(self, text: str) -> str: ...
    def mask(self, value: Any) -> Any: ...   # 递归
```

- 键名命中 `_FIELD_KEY_MARKERS`（子串、不区分大小写）→ 值替换 `***`，追加 `<key>_masked: true`。
- 内置值 pattern 不可关闭；`extra_patterns` 来自 YAML `masking.extra_patterns`。
- 保守策略：宁可误杀，不可漏放。

### audit.py — 结构化审计（默认开启、不可关闭）

```python
_MAX_PARAM_LENGTH = 200

class AuditLogger:
    def __init__(self, file_path: str | None = None, masking: MaskingEngine | None = None) -> None: ...
    @property
    def file_path(self) -> str | None: ...
    def emit(self, **event: Any) -> None: ...   # JSONL → stderr(+可选文件)
```

- 每次工具调用 emit 一条 JSONL，字段：`ts/event/tool/risk/decision/rules_hit/action_taken/params/duration_ms/error_code`。
- `params` 经 `_trim_params`（单值>200 截断）+ 脱敏后落盘；**凭证永不落盘**。
- 双通道：stderr 始终；文件由 `HUAWEICLOUD_MCP_AUDIT_FILE` 或 YAML `audit.file` 启用。

### middleware.py — 唯一拦截点

```python
class GuardrailsMiddleware:
    def __init__(self, *, read_only=False, rules=None, masking=None, audit=None) -> None: ...
    @property
    def rules(self) -> list[Rule]: ...
    async def __call__(self, ctx, call_next) -> Any: ...   # ServerMiddleware 协议
```

每次 `tools/call` 调用按序经过：只读检查 → 风险声明校验 → 保护规则 → confirm 校验 → 执行 → 脱敏 → 审计。详见 [05-guardrails.md](05-guardrails.md)。

---

## 2.10 速查：服务开发者要 import 什么

| 你在写 | import 什么 |
|---|---|
| `server.py` | `build_server` |
| `main.py` | `run_standard` + 你的 `mcp` |
| `client/*.py` | `McpSettings`, `CredentialScope`, `build_credentials`, `wrap_sdk_error` |
| `service/*.py` | `McpToolError`, `assert_not_protected`, `clamp_limit`, `page_result`, `single_result` |
| `tools/*.py` | `ToolRisk`, `guard` |

下一站：[03-tools.md](03-tools.md) 讲工具层怎么写。
