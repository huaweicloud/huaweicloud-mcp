# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Huawei Cloud RFS MCP Server entrypoint."""

from mcp_server_rfs.server import mcp
from huaweicloud_mcp_core.server import run_standard


def main() -> None:
    run_standard(mcp, service_name="rfs")


if __name__ == "__main__":
    main()
