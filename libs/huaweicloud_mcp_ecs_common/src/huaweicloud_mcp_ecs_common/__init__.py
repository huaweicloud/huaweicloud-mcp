# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Shared utilities for Huawei Cloud ECS MCP servers (ecs & ecs-lifecycle)."""

from huaweicloud_mcp_ecs_common.convert import sdk_to_dict
from huaweicloud_mcp_ecs_common.paginate import paginate
from huaweicloud_mcp_ecs_common.throttle import call_sdk

__all__ = ["call_sdk", "paginate", "sdk_to_dict"]
