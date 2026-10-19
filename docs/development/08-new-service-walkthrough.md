# 08 · 实战：从零写一个 VPC MCP Server

> 本章用 `server/mcp_server_vpc/`当主线，手把手演示从零到 PR 的全流程。阅读时可对照 `server/mcp_server_vpc/` 与 `docs/development/template/` 脚手架的真实代码。
> 目标读者：熟 Python + async + pytest，但不熟 MCP / 华为云 SDK。

## 8.0 本章产物

| 产物 | 位置 | 验证状态 |
|---|---|---|
| 脚手架模板 | `docs/development/template/` | 可运行最小骨架 |
| VPC 参考服务 | `server/mcp_server_vpc/` | ruff✓ / mypy strict✓ / 26 测试✓ / 覆盖率 92% |
| 4 个场景工具 | list_vpcs(READ) / list_subnets(READ) / create_security_group(WRITE) / delete_vpc(DANGEROUS) | 覆盖三级风险 + 护栏双防线 |

## 8.1 第一步：提案与场景调研

接入新服务**必须**先提 issue（模板 `.github/ISSUE_TEMPLATE/new-service.md`），写清：

- 服务名：`vpc`
- 目标场景清单（5–15 个，我们首版选 4 个高频场景）
- 风险级别分布（READ×2 / WRITE×1 / DANGEROUS×1，正好覆盖三级）
- 预计工具数：4

场景调研的四个来源（见 [03-tools.md §3.2](03-tools.md)）：控制台高频操作、最佳实践、FAQ 工单、Agent 目标任务。VPC 的高频操作是：看有哪些 VPC、看某 VPC 下的子网、建安全组、下线 VPC——正好对应我们的 4 个工具。

## 8.2 第二步：从 template 拷贝脚手架

```bash
cp -r docs/development/template server/mcp_server_vpc
```

然后**全局替换命名三件套**（见 [01-architecture.md](01-architecture.md)）：

| PLACEHOLDER | 替换为 |
|---|---|
| `mcp_server_PLACEHOLDER`（dist 名） | `mcp_server_vpc` |
| `mcp_server_PLACEHOLDER`（import 名/目录名） | `mcp_server_vpc` |
| `PLACEHOLDER`（service_name、SDK 包名等） | `vpc` |

替换后 `pyproject.toml` 的关键三行：

```toml
[project]
name = "mcp_server_vpc"
[project.scripts]
mcp_server_vpc = "mcp_server_vpc.main:main"
[tool.hatch.build.targets.wheel]
packages = ["src/mcp_server_vpc"]
```

> dist 名 ≠ import 名，hatchling 无法自动定位包——`[tool.hatch.build.targets.wheel] packages` 必须显式配置。

## 8.3 第三步：client 层（对照 API 文档，自底向上开发）

开发顺序：**client → service → tools**（自底向上，每层可独立测试）。

### 8.3.1 查 API 文档，确定 SDK 类与方法

VPC v3 API（https://support.huaweicloud.com/api-vpc/）：
- `ListVpcsRequest` → 列 VPC
- `ShowVpcRequest` → 查单个 VPC（404 → 不存在）
- `ListVirsubnetsRequest` → 列子网（v3 子网叫 virsubnet，方法 `list_virsubnets`）
- `CreateSecurityGroupRequest` + `CreateSecurityGroupOption` → 建安全组
- `DeleteVpcRequest` → 删 VPC

> **踩坑点**：v3 子网叫 "virsubnet"，方法名是 `list_virsubnets`，不是 `list_subnets`。v3 `CreateSecurityGroupOption` **没有 `vpc_id` 字段**（安全组是账号级，非 VPC 级）——这类 SDK 实际与设计意图不符的地方，用注释标清，service 层做补偿（见 8.4）。

### 8.3.2 写 client

`src/mcp_server_vpc/client/vpc_client.py` 关键结构（完整见 `server/mcp_server_vpc/`）：

```python
class VpcClient:
    def __init__(self, settings: McpSettings | None = None, sdk_client: Any = None) -> None:
        self._settings = settings or McpSettings.from_env()
        if sdk_client is not None:
            self._client = sdk_client          # 测试注入
        else:
            from huaweicloudsdkvpc.v3 import VpcClient as _SdkVpcClient
            from huaweicloudsdkvpc.v3.region.vpc_region import VpcRegion
            self._client = (
                _SdkVpcClient.new_builder()
                .with_credentials(build_credentials(CredentialScope.PROJECT, self._settings))
                .with_region(VpcRegion.value_of(self._settings.region))
                .build()
            )

    async def list_vpcs(self, *, limit: int, marker: str | None) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            from huaweicloudsdkvpc.v3.model.list_vpcs_request import ListVpcsRequest
            request = ListVpcsRequest(limit=limit, marker=marker)
            return cast(dict[str, Any], sdk_to_dict(self._client.list_vpcs(request)))
        return await asyncio.to_thread(_call)

    async def get_vpc(self, vpc_id: str) -> dict[str, Any] | None:
        def _call() -> dict[str, Any] | None:
            from huaweicloudsdkvpc.v3.model.show_vpc_request import ShowVpcRequest
            request = ShowVpcRequest(vpc_id=vpc_id)
            try:
                response = self._client.show_vpc(request)
            except ServiceResponseException as exc:
                if exc.status_code == 404:
                    return None
                raise wrap_sdk_error(exc) from exc
            return cast(dict[str, Any], sdk_to_dict(response))
        return await asyncio.to_thread(_call)
    ...（其余方法同构）
```

**设计要点**（VPC 实战踩出来的）：

1. **SDK 导入用 lazy import**（写在构造函数 else 分支 + 每个方法的 `_call` 内）。这样模块在 SDK 未安装时也能 import，service/tools 测试层注入 fake 就能跑，不用非得 `uv sync` 装 SDK。这是 VPC 相对 RFS（顶层导入）的改进。
2. **SDK 缺类型 stub**：在 `pyproject.toml` 加 mypy override：
   ```toml
   [[tool.mypy.overrides]]
   module = ["huaweicloudsdkcore.*", "huaweicloudsdkvpc.*"]
   ignore_missing_imports = true
   ```
   配合方法返回处的 `cast(dict[str, Any], ...)`，mypy strict 全绿。
3. **404 → None**：`get_vpc` 的 404 映射为 `None`，由 service 决定抛 `MCP_NOT_FOUND` 还是当"不存在"处理。
4. **`asyncio.to_thread` 包装**：SDK 是同步的，async 工具直接 await 会阻塞事件循环。

### 8.3.3 client 层测试

`tests/test_client.py` 注入 `RecordingSdkClient`（实现 SDK 同名方法），验证请求组装：

```python
async def test_list_vpcs_request() -> None:
    pytest.importorskip("huaweicloudsdkvpc")   # 真 SDK 请求构造测试，跳过无 SDK 环境
    sdk = RecordingSdkClient()
    result = await _client(sdk).list_vpcs(limit=20, marker="m-1")
    assert result == {"recorded": "list_vpcs"}
    method, request = sdk.requests[0]
    assert method == "list_vpcs"
    assert request.limit == 20                    # 验证 SDK Request 字段
```

> `importorskip` 让无 SDK 环境跳过这些测试；service/tools 层测试用 fake，不受影响。详见 [07-testing.md](07-testing.md)。

## 8.4 第四步：service 层（编排 + 裁剪 + 护栏）

`src/mcp_server_vpc/service/vpc_service.py`。四个场景方法对应四个工具。

### 8.4.1 字段白名单 + 分页（list_vpcs / list_subnets）

```python
_VPC_FIELDS = ("id", "name", "status", "cidr", "created_at")
_SUBNET_FIELDS = ("id", "name", "cidr", "gateway_ip", "vpc_id", "availability_zone", "status")

def _pick(source, fields):
    return {key: source[key] for key in fields if source.get(key) is not None}

async def list_vpcs(self, *, name=None, limit=20, marker=None) -> dict:
    limit = clamp_limit(limit)                       # 1..100
    response = await self._client.list_vpcs(limit=limit, marker=marker)
    vpcs = [_pick(vpc, _VPC_FIELDS) for vpc in response.get("vpcs") or []]
    if name:                                          # 内存过滤（SDK 不支持时）
        vpcs = [v for v in vpcs if name.lower() in str(v.get("name","")).lower()]
    next_marker = (response.get("page_info") or {}).get("next_marker")
    return page_result(vpcs, total=None, marker=next_marker)
```

### 8.4.2 编排：校验 + 创建（create_security_group）

这里演示"虽然 v3 安全组不带 vpc_id，但工具仍校验 VPC 存在"——编排的附加值：

```python
async def create_security_group(self, *, name, vpc_id, description=None) -> dict:
    vpc = await self._client.get_vpc(vpc_id)          # 校验 VPC 存在
    if vpc is None:
        raise McpToolError(code="MCP_NOT_FOUND", message=f"VPC '{vpc_id}' not found.",
            hint="Run list_vpcs to see existing VPCs in this region.")
    created = await self._client.create_security_group(
        name=name, vpc_id=vpc_id, description=description)   # fake 仍带 vpc_id 便于测试
    payload = _pick(created, _SECURITY_GROUP_FIELDS)
    return single_result(payload, hints=[
        "Attach this security group to ECS NICs via the ECS service.",
        "Add ingress/egress rules from the console or the VPC SDK.",
    ])
```

### 8.4.3 DANGEROUS：confirm + 第二防线（delete_vpc）

这是全章重点——三级防线在一个工具里全部出现：

```python
async def delete_vpc(self, *, vpc_id, confirm=False) -> dict:
    vpc = await self._client.get_vpc(vpc_id)
    if vpc is None:
        raise McpToolError(code="MCP_NOT_FOUND", ...)        # 不存在直接抛
    subnets_raw = await self._client.list_subnets(vpc_id=vpc_id, limit=100, marker=None)
    subnets = [_pick(s, _SUBNET_FIELDS) for s in subnets_raw.get("subnets") or []]
    if not confirm:                                          # 防线 2：confirm 预览
        return {
            "confirmation_required": True,
            "preview": {
                "vpc_id": vpc.get("id"), "name": vpc.get("name"),
                "status": vpc.get("status"), "cidr": vpc.get("cidr"),
                "tags": vpc.get("tags") or {},               # 必须回显 tags
                "subnet_count": len(subnets),
                "subnets": [{"id": s.get("id"), "name": s.get("name")} for s in subnets],
            },
            "message": "This operation is irreversible...Call again with confirm=true to proceed.",
        }
    # 防线 3：assert_not_protected 第二防线（云上真实属性二次校验）
    assert_not_protected(
        {"id": str(vpc.get("id") or ""), "name": str(vpc.get("name") or ""),
         "tags": vpc.get("tags") or {}},
        tool_name="delete_vpc",
    )
    await self._client.delete_vpc(vpc_id=vpc_id)
    return {"vpc_id": vpc_id, "deleted": True,
            "hints": ["Deletion runs asynchronously; verify with list_vpcs."]}
```

三道防线：①middleware 参数级匹配（自动，stack_name 在保护名单直接 block）；②service confirm 分支；③`assert_not_protected` 用云上真实 tags 二次校验。

### 8.4.4 service 层测试

`tests/test_service.py` 注入 `FakeVpcClient`，测编排、钳制、confirm、护栏：

```python
async def test_delete_blocked_by_protection_rule(service, fake_client, monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_MCP_PROTECTED_NAMES", "prod-vpc")
    register_vpc(fake_client, "vpc-1", name="prod-vpc")
    with pytest.raises(McpToolError) as excinfo:
        await service.delete_vpc(vpc_id="vpc-1", confirm=True)
    assert excinfo.value.code == "MCP_GUARDRAIL_BLOCKED"
    assert all(call[0] != "delete_vpc" for call in fake_client.calls)  # 真删除没发生
```

## 8.5 第五步：tools 层（极薄，注册 + guard + docstring）

`src/mcp_server_vpc/tools/vpc.py`，每个工具就一行调 service：

```python
@mcp.tool()
@guard(risk=ToolRisk.DANGEROUS)
async def delete_vpc(vpc_id: str, confirm: bool = False) -> dict[str, Any]:
    """Delete a VPC and its subordinate resources (irreversible).

    Scenario: user wants to tear down a VPC. With confirm=false the tool
    returns a preview (subnets, security groups, status, tags); call again
    with confirm=true to actually delete.

    Args:
        vpc_id: VPC UUID to delete (run list_vpcs first).
        confirm: must be explicitly true to execute; false returns a preview.
    """
    return await VpcService().delete_vpc(vpc_id=vpc_id, confirm=confirm)
```

装饰器顺序：`@mcp.tool()` 外、`@guard` 内。`server.py` 末尾 import 注册：

```python
mcp = build_server("vpc")
from mcp_server_vpc.tools import vpc  # noqa: E402,F401
```

`tests/test_tools.py` 测注册完整性、@guard 标注、参数透传、错误信封（详见 [07-testing.md §7.6](07-testing.md)）。

## 8.6 第六步：自测全绿

```bash
cd server/mcp_server_vpc
uv sync
uv run ruff check && uv run ruff format --check   # 风格
uv run mypy                                         # 类型（strict）
uv run pytest --cov                                 # 测试 + 覆盖率 ≥ 80%
uv run mcp_server_vpc                          # stdio smoke
uv run mcp_server_vpc -t streamable-http       # http smoke
```

VPC 当前状态：**ruff✓ / mypy strict✓（0 issues）/ 26 测试✓ / 覆盖率 92%**。

## 8.7 第七步：双语 README

补 `README.md`（英文）+ `README_zh.md`（中文），章节顺序固定（见 [09-engineering-release.md §9.4](09-engineering-release.md)）：

- Version / Overview / Category / Features
- **Available Tools**（逐个链接华为云官方 API 文档）
- Usage Guide（Prerequisites / Installation）
- Configuration（环境变量表 + **保护名单盲区声明**）
- Run with uvx（PyPI 版 + git subdirectory 版 JSON，可直接复制）
- Examples / License

> 保护名单盲区声明是 spec §7.9 强制项，VPC README 已声明：参数级匹配有盲区，`delete_vpc` 用 `assert_not_protected` 做第二防线弥补。

## 8.8 第八步：更新仓库总表 + PR

- 更新仓库根 `README.md` 服务总表，加一行 VPC。
- 填 PR 模板审查清单（见 [09-engineering-release.md §9.5](09-engineering-release.md)）：
  - [ ] 命名三件套一致
  - [ ] 严格三层，无跨层 import
  - [ ] 每个工具有 @guard；DANGEROUS 有 confirm
  - [ ] 英文 docstring 完整
  - [ ] 列表走 page_result，字段白名单裁剪
  - [ ] 错误统一 JSON，无裸异常
  - [ ] 凭证只来自环境变量
  - [ ] 只读模式拦截有测试
  - [ ] DANGEROUS 编排调 assert_not_protected（有测试）
  - [ ] confirm 预览回显 name/tags
  - [ ] block/warn/confirm 三类规则各有命中测试
  - [ ] 未绕过护栏
  - [ ] README 声明盲区 + 护栏配置示例
  - [ ] mypy strict✓ 覆盖率≥80% CI 全绿
  - [ ] 双语 README 齐全
  - [ ] uv.lock 已提交
- 两名 reviewer 通过（至少一名核心包维护者）方可合入。

## 8.9 踩坑实录（VPC 开发中真实遇到）

| 坑 | 现象 | 解法 |
|---|---|---|
| v3 子网叫 virsubnet | `import list_subnets_request` → ModuleNotFoundError | 改用 `list_virsubnets_request.ListVirsubnetsRequest` + 方法 `list_virsubnets` |
| 安全组 option 无 vpc_id | `CreateSecurityGroupOption(name=, vpc_id=)` → TypeError | option 只传 name/description；service 层单独校验 VPC 存在（编排附加值） |
| SDK 缺类型 stub | mypy 报 import-untyped ×20+ | pyproject 加 mypy override `ignore_missing_imports`；返回处 `cast` |
| 顶层 SDK 导入致测试难跑 | import 模块即需 SDK 安装 | 改 lazy import，service/tools 测试注入 fake 可无 SDK 运行 |
| RfsClient fake 注入 arg-type | FakeVpcClient 不是 VpcClient 子类 | fixture 处 `# type: ignore[arg-type]  # fake injection` |

下一站：[09-engineering-release.md](09-engineering-release.md) 讲工程化与发布。
