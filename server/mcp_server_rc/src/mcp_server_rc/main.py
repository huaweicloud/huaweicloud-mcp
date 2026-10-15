"""Huawei Cloud RC MCP Server entrypoint."""

from huaweicloud_mcp_core.server import run_standard

from mcp_server_rc.server import mcp


def main() -> None:
    run_standard(mcp, service_name="rc")


if __name__ == "__main__":
    main()
