# mcp-server-ecs-common

> **Language:** English | [中文](./README.md)

Shared utilities for the Huawei Cloud ECS MCP server family. This package
serves the **ecs-readonly** (`mcp_server_ecs_readonly`) and **ecs-lifecycle**
(`mcp_server_ecs_lifecycle`) server packages so that the two do not duplicate
SDK-response conversion and pagination logic.

## Contents

- `sdk_to_dict(obj)` — recursively convert a `huaweicloudsdk` response object
  into plain JSON-compatible data (handles scalars, bytes, dicts, lists,
  objects with `to_dict()`, and objects exposing a `__dict__`).
- `paginate(fetch, *, result_key, page_size, max_pages=None, advance=None)` —
  collect every item a paged list endpoint returns, sharing one pagination
  loop shape across servers / flavors / subnets etc.

## Development

This package is a local path dependency of `mcp-server-ecs-readonly` and
`mcp-server-ecs-lifecycle`. It has no runtime dependencies beyond the standard
library.

```bash
uv run pytest
```
