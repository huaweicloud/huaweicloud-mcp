# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Huawei Cloud ecs MCP Server entrypoint."""

from huaweicloud_mcp_core.server import run_standard

from mcp_huaweicloud_ecs_readonly.server import mcp


def main() -> None:
    run_standard(mcp, service_name="ecs")


if __name__ == "__main__":
    main()
