# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

from huaweicloud_mcp_core.server import build_server

mcp = build_server("PLACEHOLDER")

# import 即注册：tools 包内每个模块都会向该实例注册工具
# 注意：必须在 mcp 赋值之后再 import，避免循环导入
from mcp_server_PLACEHOLDER.tools import resource  # noqa: E402,F401
