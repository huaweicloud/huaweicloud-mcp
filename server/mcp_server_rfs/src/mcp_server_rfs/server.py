# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""FastMCP instance construction for the RFS server (guardrails auto-installed)."""

from starlette.responses import JSONResponse

from huaweicloud_mcp_core.server import build_server

mcp = build_server("rfs")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request) -> JSONResponse:
    """Lightweight liveness probe used by the MCP client/agent.

    The standard MCP protocol runs on /mcp; clients that probe /health
    otherwise get a 404. This returns 200 {"status":"ok","service":"rfs"} so
    the agent's readiness check passes.
    """
    return JSONResponse({"status": "ok", "service": "rfs"})


from mcp_server_rfs.tools import stack  # noqa: E402,F401
