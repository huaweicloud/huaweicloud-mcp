# 09 · 工程化与发布

## 9.1 包管理与构建（uv）

- 统一使用 **uv**：`uv sync` 安装、`uv run <cmd>` 执行、`uv build` 构建；`uv.lock` **必须**提交。
- Python 基线 `>=3.10`；本地推荐 3.10/3.12 双版本验证。
- monorepo 本地联调用 `[tool.uv.sources]` path 依赖指向核心包：

  ```toml
  [tool.uv.sources]
  huaweicloud-mcp-core = { path = "../../libs/huaweicloud_mcp_core" }
  ```

发布时由 release 流程剥离 path 依赖（PyPI 版本用范围 `huaweicloud-mcp-core>=1.0,<2`）。

## 9.2 代码风格（必须）

### ruff

```toml
[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]
```

CI 执行 `ruff check` + `ruff format --check`。本地可 `ruff check --fix` + `ruff format` 自动修。

### mypy strict

```toml
[tool.mypy]
strict = true
python_version = "3.10"
```

全部代码（含 tests）类型完整。SDK 缺 stub 时允许局部 `# type: ignore[...]` 并注明原因，或用 mypy override：

```toml
[[tool.mypy.overrides]]
module = ["huaweicloudsdkcore.*", "huaweicloudsdkvpc.*"]
ignore_missing_imports = true
```

> **当前状态**：核心包已加 `py.typed` 标记（mypy 能识别其类型）。华为云 SDK 仍缺 stub，用 override 处理。各服务应达到 mypy strict 零 issue（VPC 参考服务已达成）。

## 9.3 测试基线

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "mypy>=1.10",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=80"
```

- `--cov-fail-under=80` 是 CI 硬门槛。
- `asyncio_mode = "auto"`：测试函数写 `async def` 即可，无需 `@pytest.mark.asyncio`。
- **禁止**在 CI 调用真实云 API；建议额外提供 `tests/smoke/`（默认跳过，`-m smoke` 手动执行）。
- 三层测试策略详见 [07-testing.md](07-testing.md)。

## 9.4 文档规范（双语 README 固定章节）

每个服务**必须**提供 `README.md`（英文）+ `README_zh.md`（中文），内容等价，章节顺序固定：

```markdown
# <Service> MCP Server
## Version                     # x.y.z，与 pyproject.toml 一致
## Overview                    # 一段话：服务定位 + 面向的场景
## Category                    # 计算/存储/数据库/网络/...（对齐仓库 README 分类）
## Features                    # 能力要点列表
## Available Tools             # 工具清单表格：名称 | 场景说明 | 风险级别 | API 文档链接
## Usage Guide
### Prerequisites              # Python 3.10+ / uv 安装命令
### Installation               # git clone + uv run 启动（含 -t streamable-http）
## Configuration
### Environment Variables      # 变量表（全集 + 服务自定义变量）
### Run with uvx               # PyPI 版与 git subdirectory 版两份 client JSON 配置示例
## Examples                    # Cursor / Trae / Claude Desktop 配置示例
## License
```

- 工具清单**必须**逐个链接华为云官方 API 文档。
- `Run with uvx` 的 JSON 示例**必须**可直接复制运行。
- 服务 README **必须**声明保护名单的参数级匹配盲区（spec §7.9 强制），并给护栏配置示例。
- 仓库级 `README.md` 维护服务总表（分类 + 链接 + 一句话简介），新服务合入时同步更新。

## 9.5 CI 与 PR 流程（GitHub Actions）

`ci.yml` 按变更路径触发（`server/mcp_server_<service>/**` 只跑该服务 + 核心包任务）：

1. `uv sync` → 2. `ruff check && ruff format --check` → 3. `mypy` → 4. `pytest --cov` → 5. 规范自检脚本：
   - 每个注册工具均有 `@guard(risk=...)`
   - DANGEROUS 工具均有 `confirm` 参数
   - DANGEROUS 工具的 service 编排调用了 `assert_not_protected`
   - 服务未卸载/替换 `GuardrailsMiddleware`（build_server 调用链未被篡改）
   - README.md 与 README_zh.md 均存在且含必需章节
   - dist/import/script 三名一致
   - 提交 guardrails.yaml 时通过核心包 schema 校验

**PR 必须 CI 全绿才可合入。** 审查清单：

- [ ] 命名三件套一致，pyproject 显式 `[tool.hatch.build.targets.wheel] packages`
- [ ] 严格三层，无跨层 import
- [ ] 每个工具有 `@guard`；DANGEROUS 有 `confirm` 且 `confirm=false` 无副作用
- [ ] 完整英文 docstring（Scenario / Args / Returns / 前置依赖）
- [ ] 列表走 `page_result`，limit 默认 20 上限 100，字段白名单裁剪
- [ ] 错误统一 JSON（code/message/request_id/hint），无裸异常
- [ ] 凭证只来自环境变量，日志与输出无 AK/SK/token
- [ ] 只读模式拦截 WRITE/DANGEROUS（有测试）
- [ ] DANGEROUS 编排调 `assert_not_protected`（有测试）
- [ ] confirm 预览回显 name/tags
- [ ] block/warn/confirm 三类规则各有命中测试
- [ ] 未绕过护栏
- [ ] README 声明盲区 + 护栏配置示例
- [ ] mypy strict✓、覆盖率 ≥ 80%、CI 全绿
- [ ] 双语 README 齐全、章节完整、工具清单带官方文档链接
- [ ] 未修改核心包公共接口（如需修改，单独提 PR + 迁移说明）
- [ ] uv.lock 已提交，依赖版本合理（SDK `>=x.y`，核心包 `>=1.0,<2`）

两名 reviewer 通过（至少一名核心包维护者）方可合入。

## 9.6 传输协议规范

1. **必须**同时支持 `stdio`（默认）+ `streamable-http`，`-t/--transport` 选择（核心包 `run_standard` 提供，服务不得自行 argparse）。
2. streamable-http 监听地址/端口由 `MCP_SERVER_HOST`/`MCP_SERVER_PORT` 控制，默认 `0.0.0.0:8000`。
3. **stdio 模式 stdout 必须绝对干净**（任何 `print`、第三方库向 stdout 写日志都会破坏 stdio 传输）。日志统一 stderr；核心包 `logging` 默认 `StreamHandler(sys.stderr)`。CI 自检含"源码无裸 print"。
4. 服务**不得**自行处理 MCP 协议层细节（握手、capabilities），交给 `mcp` SDK。

## 9.7 版本规范

### 版本号（semver，每包独立）

- **MAJOR**：工具删除/重命名、参数不兼容变更、输出结构破坏性变更
- **MINOR**：新增工具 / 新增可选参数
- **PATCH**：修复、描述优化、依赖升级

版本号唯一事实源是各包 `pyproject.toml`；tag 格式 `mcp_server_<service>/vx.y.z`（核心包 `huaweicloud-mcp-core/vx.y.z`）。

### 源码发布

1.  **git subdirectory**：始终可安装：
   ```json
   {
     "mcpServers": {
       "huaweicloud-vpc": {
         "command": "uvx",
         "args": ["--from", "git+https://github.com/huaweicloud/huaweicloud-mcp#subdirectory=server/mcp_server_vpc", "mcp_server_vpc"],
         "env": { "HUAWEICLOUD_ACCESS_KEY": "", "HUAWEICLOUD_SECRET_KEY": "", "HUAWEICLOUD_REGION": "" }
       }
     }
   }
   ```

### 依赖策略

- 服务依赖核心包用范围 `huaweicloud-mcp-core>=MAJOR,<MAJOR+1`；核心包破坏性变更必须先发迁移文档再升 MAJOR。
- huaweicloudsdk 依赖允许 `>=` 浮动，锁文件保证可复现。

## 9.8 当前仓库工程化状态（坦白）

| 项 | 状态 |
|---|---|
| uv + ruff | 全包已配，VPC 参考服务 ruff 全绿 |
| mypy strict | 核心包已加 `py.typed`；VPC 参考服务 mypy 零 issue；RFS 尚有 SDK stub 相关遗留 |
| pytest 覆盖率 | VPC 92%、RFS 全绿；`--cov-fail-under=80` 硬门槛已配 |
| CI workflow（`.github/workflows/ci.yml`） | **尚未落地**，属待补缺口 |
| `release.yml`（PyPI 发布） | **尚未落地**，属待补缺口 |
| PR / Issue 模板 | spec 引用，**尚未落地**，属待补缺口 |
| CONTRIBUTING.md / LICENSE / 仓库 README_zh | spec 引用，**尚未落地**，属待补缺口 |

> 这些缺口不影响服务开发与自测（本地 `uv run ruff && uv run mypy && uv run pytest` 全套可用），但合入前需补齐 CI 与模板。详见各篇"清单"。

## 9.9 验证命令速查

```bash
cd server/mcp_server_<service>
uv sync
uv run ruff check && uv run ruff format --check    # 风格
uv run mypy src tests                               # 类型（strict）
uv run pytest --cov                                 # 测试 + 覆盖率
uv run mcp_server_<service>                # stdio smoke
uv run mcp_server_<service> -t streamable-http   # http smoke
```

返回 [README.md](README.md)。
