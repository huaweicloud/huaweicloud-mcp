# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the masking engine."""

from __future__ import annotations

from huaweicloud_mcp_core.guardrails.masking import MASK, MaskingEngine


def test_masks_huawei_cloud_ak_in_text() -> None:
    engine = MaskingEngine()
    text = "credential AKLPTQWERTYUIOP1 in logs"
    assert "AKLPTQWERTYUIOP1" not in engine.mask_text(text)
    assert MASK in engine.mask_text(text)


def test_masks_huawei_cloud_sk_in_text() -> None:
    engine = MaskingEngine()
    sk = "a" * 40
    assert engine.mask_text(f"sk={sk}") == f"sk={MASK}"


def test_masks_pem_private_key_block() -> None:
    engine = MaskingEngine()
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n-----END RSA PRIVATE KEY-----"
    masked = engine.mask_text(text)
    assert "MIIEow" not in masked
    assert MASK in masked


def test_masks_bearer_tokens() -> None:
    engine = MaskingEngine()
    masked = engine.mask_text("Authorization: Bearer abc123DEF-_+/==")
    assert "abc123DEF" not in masked


def test_masks_sensitive_dict_keys() -> None:
    engine = MaskingEngine()
    payload = {
        "server": {"admin_password": "hunter2", "name": "web-1"},
        "auth_token": "tok",
        "tags": {"env": "prod"},
    }
    masked = engine.mask(payload)
    assert isinstance(masked, dict)
    server = masked["server"]
    assert server["admin_password"] == MASK
    assert server["admin_password_masked"] is True
    assert server["name"] == "web-1"
    assert masked["auth_token"] == MASK
    assert masked["tags"] == {"env": "prod"}


def test_masks_nested_lists() -> None:
    engine = MaskingEngine()
    payload = {"users": [{"secret": "s1"}, {"name": "alice"}]}
    masked = engine.mask(payload)
    assert masked["users"][0]["secret"] == MASK
    assert masked["users"][1]["name"] == "alice"


def test_custom_extra_patterns() -> None:
    engine = MaskingEngine(extra_patterns=(("corp-key", r"corpkey-[a-z0-9]{8}"),))
    masked = engine.mask_text("value corpkey-abcd1234 end")
    assert "corpkey-abcd1234" not in masked
    assert MASK in masked


def test_plain_values_untouched() -> None:
    engine = MaskingEngine()
    payload = {"stack_name": "web-app-prod", "status": "DEPLOYMENT_COMPLETE"}
    assert engine.mask(payload) == payload
