# 07 · 单元测试开发

> 参考实现：`server/mcp_server_rfs/tests/`（test_client.py / test_service.py / test_tools.py / conftest.py）。
> 本章贴 RFS 真实测试代码，讲清每层"测什么、怎么注入、断言什么"。

## 7.1 测试基线（硬门槛）

- **pytest**，目录 `tests/`，与 `src/` 平级；`--cov-fail-under=80` 为 CI 硬门槛。
- async 测试用 `pytest-asyncio`（`asyncio_mode = "auto"`，测试函数写 `async def` 即可，无需 `@pytest.mark.asyncio`）。
- **禁止**在 CI 中调用真实云 API；建议额外提供 `tests/smoke/`（默认跳过，`-m smoke` 手动执行）用于本地真连验证。

### pyproject.toml 测试配置（RFS 范本）

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=80"
```

## 7.2 测试分层总览

三层各有自己的注入点和断言重点：

| 层 | 测试文件 | 注入什么 | 断言什么 |
|---|---|---|---|
| client | `test_client.py` | 假 SDK Client（`RecordingSdkClient`，实现 SDK 方法名） | 请求组装（模型字段、vars 转换）、异常 wrap（404→None 等） |
| service | `test_service.py` | 假 client（`FakeRfsClient`，实现 client 的 async 方法名） | 编排逻辑、分页钳制、字段白名单、confirm 分支、护栏第二防线 |
| tools | `test_tools.py` | 假 service（`StubService`，monkeypatch `StackService`） | 注册完整性、`@guard` 标注、只读拦截、错误 JSON 结构 |

注意三层注入的"假"形态不同：
- client 测试注入**假 SDK Client**（同步方法 `list_stacks(request)`）。
- service 测试注入**假 client**（async 方法 `await list_stacks(...)`）。
- tools 测试注入**假 service**（async 方法，但 monkeypatch 类）。

## 7.3 conftest.py — 共享 fixture 与环境隔离

### 隔离环境变量（autouse）

测试必须隔离真实环境，避免凭证/只读/护栏配置污染。RFS conftest 用 `monkeypatch.delenv` 清空全部相关变量：

```python
_ENV_KEYS = [
    "HUAWEICLOUD_ACCESS_KEY", "HUAWEICLOUD_SECRET_KEY", "HUAWEICLOUD_REGION",
    "HUAWEICLOUD_PROJECT_ID", "HUAWEICLOUD_SECURITY_TOKEN", "HUAWEICLOUD_ENDPOINT",
    "HUAWEICLOUD_MCP_READ_ONLY",
    "HUAWEICLOUD_MCP_PROTECTED_IDS", "HUAWEICLOUD_MCP_PROTECTED_NAMES",
    "HUAWEICLOUD_MCP_PROTECTED_TAGS",
    "HUAWEICLOUD_MCP_GUARDRAILS_CONFIG", "HUAWEICLOUD_MCP_AUDIT_FILE",
    "MCP_SERVER_PORT", "MCP_SERVER_HOST",
]

@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
```

`autouse=True` 每个测试自动应用，保证起点干净。需要护栏规则时，测试自己 `monkeypatch.setenv` 临时设。

### FakeRfsClient — service 层测试用的假 client

`FakeRfsClient` 实现 client 的 async 方法名，内部用 dict 存数据，记录每次调用：

```python
class FakeRfsClient:
    def __init__(self) -> None:
        self.stacks: dict[str, dict] = {}
        self.resources: dict[str, list[dict]] = {}
        self.events: dict[str, list[dict]] = {}
        self.outputs: dict[str, list[dict]] = {}
        self.plans: dict[str, dict] = {}
        self.status_queue: list[str] = []          # 模拟状态流转
        self.plan_status_queue: list[str] = []
        self.calls: list[tuple[str, dict]] = []    # 记录调用
        self.next_marker: str | None = None
        self.deploy_response: dict = {"deployment_id": "dep-42"}
        self.create_response: dict = {"stack_id": "sid-new"}

    async def list_stacks(self, *, limit, marker) -> dict:
        self.calls.append(("list_stacks", {"limit": limit, "marker": marker}))
        items = list(self.stacks.values())
        return {"stacks": items[:limit], "page_info": {"next_marker": self.next_marker}}

    async def get_stack_metadata(self, stack_name) -> dict | None:
        self.calls.append(("get_stack_metadata", {"stack_name": stack_name}))
        if self.status_queue:                      # 模拟状态变化
            status = self.status_queue.pop(0)
            if stack_name in self.stacks:
                self.stacks[stack_name]["status"] = status
        return self.stacks.get(stack_name)
    ...（每个 client 方法都实现）...

@pytest.fixture
def fake_client() -> FakeRfsClient:
    return FakeRfsClient()

def register_stack(client, name, status="DEPLOYMENT_COMPLETE", **extra) -> dict:
    stack = {"stack_id": f"sid-{name}", "stack_name": name, "status": status,
             "status_message": None, "description": f"stack {name}",
             "create_time": "2026-01-01T00:00:00Z", "enable_deletion_protection": False}
    stack.update(extra)
    client.stacks[name] = stack
    return stack
```

要点：
- `calls` 列表记录每次调用（方法名 + 参数），测试用它断言"真删除没发生""调了哪个方法"。
- `status_queue` / `plan_status_queue` 模拟异步状态流转，测轮询等待。
- `register_stack` 辅助函数快速造数据。

## 7.4 client 层测试 — 请求组装与异常映射

### 假 SDK Client：RecordingSdkClient

实现 SDK 的同步方法名，记录请求：

```python
class RecordingSdkClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, Any]] = []

    def _record(self, method, request) -> dict:
        self.requests.append((method, request))
        return {"recorded": method}

    def list_stacks(self, request) -> dict:
        return self._record("list_stacks", request)
    def create_stack(self, request) -> dict:
        return self._record("create_stack", request)
    ...（每个用到的 SDK 方法都实现）...

def _client(sdk) -> RfsClient:
    return RfsClient(settings=_SETTINGS, sdk_client=sdk)   # 注入 sdk_client
```

`_SETTINGS` 是固定配置（假 AK/SK/region），避免 `from_env` 读真实环境。

### 测请求组装（验证 SDK 模型字段、vars 转换）

```python
async def test_list_stacks_request() -> None:
    sdk = RecordingSdkClient()
    result = await _client(sdk).list_stacks(limit=20, marker="m-1")
    assert result == {"recorded": "list_stacks"}
    method, request = sdk.requests[0]
    assert method == "list_stacks"
    assert request.limit == 20                    # 验证 SDK Request 字段
    assert request.marker == "m-1"

async def test_create_stack_converts_variables() -> None:
    sdk = RecordingSdkClient()
    await _client(sdk).create_stack(
        stack_name="web", template_body="tpl", template_uri=None,
        variables={"env": "prod", "size": "3"}, enable_deletion_protection=True,
    )
    _, request = sdk.requests[0]
    assert request.body.stack_name == "web"
    assert request.body.template_body == "tpl"
    assert request.body.enable_deletion_protection is True
    converted = [
        {"var_key": item.var_key, "var_value": item.var_value}
        for item in request.body.vars_structure
    ]
    assert converted == [                          # 验证 dict → VarsStructure 转换
        {"var_key": "env", "var_value": "prod"},
        {"var_key": "size", "var_value": "3"},
    ]
```

### 测异常映射（404→None、其它→wrap_sdk_error）

```python
async def test_get_stack_metadata_maps_404_to_none() -> None:
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class NotFoundSdk(RecordingSdkClient):
        def get_stack_metadata(self, request) -> dict:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 404
            raise exc                                   # SDK 抛 404

    assert await _client(NotFoundSdk()).get_stack_metadata("ghost") is None  # → None

async def test_get_stack_metadata_wraps_other_errors() -> None:
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    class BrokenSdk(RecordingSdkClient):
        def get_stack_metadata(self, request) -> dict:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 500
            exc.error_code = "RFS.1000"
            exc.error_msg = "internal error"
            exc.request_id = "req-1"
            raise exc                                   # SDK 抛 500

    with pytest.raises(McpToolError) as excinfo:
        await _client(BrokenSdk()).get_stack_metadata("web")
    assert excinfo.value.code == "RFS.1000"             # error_code 透传
    assert excinfo.value.request_id == "req-1"          # request_id 透传
```

> `ServiceResponseException.__new__(...)` 绕过构造函数直接造实例——SDK 异常构造复杂，测试用 `__new__` + 手设属性更简单。

### 测 sdk_to_dict

```python
def test_sdk_to_dict_strips_private_prefixes() -> None:
    class Inner:
        def __init__(self): self._value = "v"
    class Outer:
        def __init__(self):
            self._name = "web"; self._status = "OK"
            self._inner = Inner(); self._items = [Inner(), Inner()]
    result = sdk_to_dict(Outer())
    assert result == {                                  # _ 前缀去掉
        "name": "web", "status": "OK",
        "inner": {"value": "v"}, "items": [{"value": "v"}, {"value": "v"}],
    }

def test_sdk_to_dict_passthrough_scalars() -> None:
    assert sdk_to_dict(None) is None
    assert sdk_to_dict("x") == "x"
    assert sdk_to_dict(5) == 5
    assert sdk_to_dict(True) is True
    assert sdk_to_dict({"a": [1, 2]}) == {"a": [1, 2]}
```

## 7.5 service 层测试 — 编排与护栏

注入 `FakeRfsClient`，测编排逻辑、分页钳制、字段白名单、confirm 分支、护栏第二防线。

### fixture：注入假 client

```python
@pytest.fixture
def service(fake_client: FakeRfsClient) -> StackService:
    return StackService(client=fake_client)        # 注入 client
```

### 测分页 + 过滤 + 钳制

```python
async def test_list_stacks_paginates_and_filters(service, fake_client) -> None:
    register_stack(fake_client, "web-prod")
    register_stack(fake_client, "web-dev")
    register_stack(fake_client, "db-prod")
    fake_client.next_marker = "marker-2"
    result = await service.list_stacks(name="web", limit=10)
    assert [item["stack_name"] for item in result["items"]] == ["web-prod", "web-dev"]
    assert result["count"] == 2
    assert result["marker"] == "marker-2"           # 下一页标记透传

async def test_list_stacks_limit_is_clamped(service, fake_client) -> None:
    register_stack(fake_client, "s1")
    result = await service.list_stacks(limit=5000) # LLM 可能传 5000
    assert fake_client.calls[-1][1]["limit"] == 100  # 钳到 100
    assert result["count"] == 1
```

### 测单对象 + 派生数据

```python
async def test_get_stack_returns_outputs(service, fake_client) -> None:
    register_stack(fake_client, "web")
    fake_client.outputs["web"] = [
        {"output_key": "eip", "output_value": "1.2.3.4"},
        {"output_key": "vpc_id", "output_value": "vpc-9"},
    ]
    result = await service.get_stack(stack_name="web")
    assert result["stack_id"] == "sid-web"
    assert result["outputs"] == {"eip": "1.2.3.4", "vpc_id": "vpc-9"}  # outputs 转 map
```

### 测"不存在"分支

```python
async def test_get_stack_missing_raises(service) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.get_stack(stack_name="nope")
    assert excinfo.value.code == "MCP_NOT_FOUND"
    assert "list_stacks" in (excinfo.value.hint or "")    # hint 含下一步工具
```

### 测编排分支（创建 vs 更新）

```python
async def test_deploy_creates_when_absent(service, fake_client) -> None:
    result = await service.deploy_stack(
        stack_name="fresh", template="resource \"huaweicloud_vpc\" \"main\" {}", variables={"env": "dev"})
    assert result["action"] == "created"
    assert fake_client.calls[-1][0] == "create_stack"     # 调了 create 不是 deploy
    assert "Track progress" in result["hints"][0]

async def test_deploy_updates_when_exists(service, fake_client) -> None:
    register_stack(fake_client, "web", status="DEPLOYMENT_COMPLETE")
    result = await service.deploy_stack(stack_name="web", template_uri="https://obs.example.com/tpl")
    assert result["action"] == "updated"
    assert result["deployment_id"] == "dep-42"
    assert fake_client.calls[-1][0] == "deploy_stack"

async def test_deploy_rejects_while_in_progress(service, fake_client) -> None:
    register_stack(fake_client, "web", status="DEPLOYMENT_IN_PROGRESS")
    with pytest.raises(McpToolError) as excinfo:
        await service.deploy_stack(stack_name="web", template="t")
    assert excinfo.value.code == "MCP_INVALID_STATE"      # 并发保护
```

### 测业务校验

```python
async def test_deploy_requires_template_argument(service) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.deploy_stack(stack_name="x")        # 既没 template 也没 template_uri
    assert excinfo.value.code == "MCP_INVALID_ARGS"
    assert "template" in excinfo.value.message

async def test_deploy_rejects_both_template_channels(service) -> None:
    with pytest.raises(McpToolError) as excinfo:
        await service.deploy_stack(stack_name="x", template="t", template_uri="u")  # 两个都给
    assert excinfo.value.code == "MCP_INVALID_ARGS"
```

### 测轮询等待（monkeypatch 跳过 sleep）

```python
async def test_deploy_wait_polls_until_complete(service, fake_client, monkeypatch) -> None:
    monkeypatch.setattr("mcp_server_rfs.service.stack_service._POLL_INTERVAL_SECONDS", 0)  # 跳过等待
    register_stack(fake_client, "web", status="DEPLOYMENT_IN_PROGRESS")
    fake_client.status_queue = ["DEPLOYMENT_COMPLETE"]    # 第一次查询后变 COMPLETE
    fake_client.outputs["web"] = [{"output_key": "eip", "output_value": "1.1.1.1"}]
    result = await service.deploy_stack(stack_name="web", template="t", wait=True, timeout_seconds=5)
    assert result["waited"] is True
    assert result["status"] == "DEPLOYMENT_COMPLETE"
    assert result["outputs"] == {"eip": "1.1.1.1"}
```

> `monkeypatch.setattr(..., "_POLL_INTERVAL_SECONDS", 0)` 是测轮询的标准套路——跳过真实 sleep，配合 `status_queue` 模拟状态流转。

### 测 DANGEROUS 的 confirm 分支

```python
async def test_delete_without_confirm_returns_preview(service, fake_client) -> None:
    register_stack(fake_client, "web")
    fake_client.resources["web"] = [
        {"resource_name": "vpc", "resource_type": "huaweicloud_vpc"},
        {"resource_name": "eip", "resource_type": "huaweicloud_vpc_eip"},
        {"resource_name": "eip2", "resource_type": "huaweicloud_vpc_eip"},
    ]
    result = await service.delete_stack(stack_name="web")   # confirm 默认 False
    assert result["confirmation_required"] is True
    assert result["preview"]["stack_name"] == "web"
    assert result["preview"]["resource_count"] == 3
    assert result["preview"]["resource_types"] == {"huaweicloud_vpc": 1, "huaweicloud_vpc_eip": 2}
    assert "tags" in result["preview"]                       # 必须回显 tags
    assert all(call[0] != "delete_stack" for call in fake_client.calls)  # 真删除没发生
```

### 测护栏第二防线（assert_not_protected）

```python
async def test_delete_blocked_by_protection_rule(service, fake_client, monkeypatch) -> None:
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_NAMES", "prod-web")  # 临时设保护名单
    register_stack(fake_client, "prod-web")
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_stack(stack_name="prod-web", confirm=True)
    assert excinfo.value.code == "MCP_GUARDRAIL_BLOCKED"
    assert all(call[0] != "delete_stack" for call in fake_client.calls)  # 真删除没发生
```

### 测 deletion_protection 业务保护

```python
async def test_delete_respects_deletion_protection(service, fake_client) -> None:
    register_stack(fake_client, "web", enable_deletion_protection=True)
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_stack(stack_name="web", confirm=True)
    assert excinfo.value.code == "MCP_DELETION_PROTECTED"
```

## 7.6 tools 层测试 — 注册、guard、错误信封

### 测注册完整性

```python
import mcp_server_rfs.server  # noqa: F401  (import 即注册所有工具)

async def test_tools_are_registered_on_server() -> None:
    from mcp_server_rfs.server import mcp
    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert tool_names == {                          # 6 个工具全注册了
        "list_stacks", "get_stack", "preview_stack_changes",
        "deploy_stack", "diagnose_stack", "delete_stack",
    }
```

### 测 @guard 风险标注

```python
from huaweicloud_mcp_core.security import ToolRisk, get_tool_risk, tool_supports_confirm

def test_all_six_tools_declare_risk() -> None:
    expected = {
        "list_stacks": ToolRisk.READ, "get_stack": ToolRisk.READ,
        "preview_stack_changes": ToolRisk.READ, "deploy_stack": ToolRisk.WRITE,
        "diagnose_stack": ToolRisk.READ, "delete_stack": ToolRisk.DANGEROUS,
    }
    for tool_name, risk in expected.items():
        assert get_tool_risk(tool_name) is risk, tool_name     # 登记表里有

def test_dangerous_tool_has_confirm_parameter() -> None:
    assert tool_supports_confirm("delete_stack") is True        # DANGEROUS 带 confirm
    assert tool_supports_confirm("deploy_stack") is False       # WRITE 不带
```

> 这是 spec §11.4 CI 自检的核心——"每个工具有 @guard、DANGEROUS 有 confirm"用 `get_tool_risk` / `tool_supports_confirm` 验证。

### 测参数透传（monkeypatch StackService）

```python
class StubService:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []
    async def list_stacks(self, *, name=None, limit=20, marker=None) -> dict:
        self.calls.append({"name": name, "limit": limit, "marker": marker})
        return self.payload
    ...（每个 service 方法都 stub）...

@pytest.fixture
def stub_service(monkeypatch) -> StubService:
    stub = StubService({"items": [], "count": 0})
    monkeypatch.setattr("mcp_server_rfs.tools.stack.StackService", lambda: stub)  # 替换类
    return stub

async def test_list_stacks_tool_passes_arguments(stub_service) -> None:
    from mcp_server_rfs.tools.stack import list_stacks
    result = await list_stacks(name="web", limit=5)
    assert result == {"items": [], "count": 0}
    assert stub_service.calls == [{"name": "web", "limit": 5, "marker": None}]   # 参数透传

async def test_delete_tool_passes_confirm(stub_service) -> None:
    from mcp_server_rfs.tools.stack import delete_stack
    await delete_stack(stack_name="web", retain_resources=True, confirm=True)
    assert stub_service.calls == [{"stack_name": "web", "retain_resources": True, "confirm": True}]
```

> `monkeypatch.setattr("...tools.stack.StackService", lambda: stub)` 把 `tools/stack.py` 里的 `StackService` 类替换成"返回 stub 的工厂"。工具函数 `await StackService().xxx()` 实际调到 stub。

### 测错误信封（@guard catch McpToolError → dict）

```python
async def test_tool_error_becomes_error_envelope(monkeypatch) -> None:
    from huaweicloud_mcp_core.errors import McpToolError

    class FailingService(StubService):
        async def get_stack(self, *, stack_name) -> dict:
            raise McpToolError("MCP_NOT_FOUND", f"Stack '{stack_name}' not found.")

    monkeypatch.setattr("mcp_server_rfs.tools.stack.StackService", lambda: FailingService({}))
    from mcp_server_rfs.tools.stack import get_stack

    result = await get_stack("ghost")
    assert result["error"]["code"] == "MCP_NOT_FOUND"     # 异常 → 错误信封
```

> 这验证了 `@guard` 的 catch 机制：service 抛 `McpToolError`，工具层 catch 后 `return exc.to_dict()`，不冒泡。

## 7.7 覆盖率：哪些路径难覆盖

`--cov-fail-under=80` 是硬门槛。几个已知难点：

| 难点 | 覆盖技巧 |
|---|---|
| 护栏 fail-closed（middleware 运行期异常） | 造非法正则规则触发 `re.error`，或 monkeypatch `evaluate_rules` 抛异常 |
| 脱敏递归（masking） | 构造嵌套 dict，含 AK/SK/密码键名，断言 `***` 和 `_masked: true` |
| streamable-http 传输 | 单测难覆盖，放 `tests/smoke/` 手动跑 |
| project_id 自动解析（IAM 调用） | monkeypatch `IamClient`，测缓存命中/未命中/解析失败三个分支 |

## 7.8 清单：合格的三层测试

**client 层**
- [ ] RecordingSdkClient 注入，测请求组装（模型字段、vars 转换）
- [ ] 404→None、其它→wrap_sdk_error（error_code/request_id 透传）
- [ ] sdk_to_dict（去 `_` 前缀、递归、标量透传）

**service 层**
- [ ] FakeRfsClient 注入，测编排分支（创建/更新/并发保护）
- [ ] 分页钳制（limit 5000→100）、字段白名单裁剪
- [ ] confirm 分支（preview 回显 name/tags、真删除没发生）
- [ ] assert_not_protected 第二防线（monkeypatch 保护名单）
- [ ] 轮询等待（monkeypatch _POLL_INTERVAL_SECONDS=0 + status_queue）

**tools 层**
- [ ] 注册完整性（`await mcp.list_tools()`）
- [ ] @guard 风险标注（get_tool_risk）
- [ ] DANGEROUS 有 confirm（tool_supports_confirm）
- [ ] 参数透传（StubService + monkeypatch）
- [ ] 错误信封（FailingService 抛 McpToolError → result["error"]["code"])

下一站：[08-new-service-walkthrough.md](08-new-service-walkthrough.md) 从零建 VPC 服务。
