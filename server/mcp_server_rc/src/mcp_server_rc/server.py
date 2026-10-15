"""MCPServer instance construction for the RC server (guardrails auto-installed)."""

from huaweicloud_mcp_core.server import build_server

mcp = build_server("rc")

from mcp_server_rc.tools import resource  # noqa: E402,F401
