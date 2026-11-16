# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the discovery service methods (image/flavor/keypair lookup)."""

from __future__ import annotations

from typing import Any

import pytest

from conftest import FakeLifecycleClient
from mcp_server_ecs_lifecycle.service.lifecycle_service import EcsLifecycleService


@pytest.fixture
def service(fake_client: FakeLifecycleClient) -> EcsLifecycleService:
    return EcsLifecycleService(client=fake_client)  # type: ignore[arg-type]


# ---------------------------------------------------------------------- images


def _image(image_id: str, name: str, **extra: Any) -> dict[str, Any]:
    image: dict[str, Any] = {
        "id": image_id,
        "name": name,
        "os_type": "Linux",
        "os_version": "Ubuntu 22.04 server 64bit",
        "status": "active",
        "imagetype": "public",
        "min_disk": 40,
        "min_ram": 2048,
        "visibility": "public",
    }
    image.update(extra)
    return image


async def test_list_images_filters_by_name_and_os_type(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.images = [
        _image("img-ubuntu-22", "Ubuntu 22.04 server 64bit"),
        _image("img-ubuntu-20", "Ubuntu 20.04 server 64bit"),
        _image("img-win", "Windows Server 2019 Datacenter 64bit", os_type="Windows"),
        _image("img-centos", "CentOS 7.9 64bit"),
    ]

    result = await service.list_images(name="ubuntu", os_type="linux")

    assert result["total"] == 2
    assert result["count"] == 2
    assert [i["id"] for i in result["items"]] == ["img-ubuntu-22", "img-ubuntu-20"]


async def test_list_images_whitelist_drops_extra_fields(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.images = [_image("img-1", "Ubuntu 22.04", __unused="x")]

    result = await service.list_images()

    assert set(result["items"][0]) == {
        "id",
        "name",
        "os_type",
        "os_version",
        "status",
        "imagetype",
        "min_disk",
        "min_ram",
        "visibility",
    }


async def test_list_images_limit_caps_returned_not_total(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.images = [_image("img-1", "Ubuntu 22.04"), _image("img-2", "Ubuntu 20.04")]

    result = await service.list_images(limit=1)
    assert result["total"] == 2
    assert result["count"] == 1

    # limit is clamped to 1-100, so 0 and negative behave like 1.
    clamped = await service.list_images(limit=0)
    assert clamped["count"] == 1


# --------------------------------------------------------------------- flavors


def _flavor(flavor_id: str, vcpus: Any, ram: int, disk: int = 40) -> dict[str, Any]:
    return {
        "id": flavor_id,
        "name": flavor_id,
        "vcpus": vcpus,  # the API returns vcpus as a string
        "ram": ram,  # MB
        "disk": disk,
        "extra_field": "dropped",
    }


async def test_list_flavors_match_vcpus_and_ram_gb(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.flavors = [
        _flavor("s6.small.1", "1", 1024),
        _flavor("s6.large.2", "2", 4096),
        _flavor("c7.xlarge.4", "4", 16384),
    ]

    result = await service.list_flavors(vcpus=2, ram_gb=4)

    assert result["total"] == 1
    assert result["items"][0]["id"] == "s6.large.2"
    # ram filtering compares MB against GB * 1024.
    assert result["items"][0]["ram"] == 4096

    none = await service.list_flavors(vcpus=2, ram_gb=8)
    assert none["total"] == 0


async def test_list_flavors_whitelist_drops_extra_fields(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.flavors = [_flavor("s6.small.1", "1", 1024)]

    result = await service.list_flavors()

    assert set(result["items"][0]) == {"id", "name", "vcpus", "ram", "disk"}


async def test_list_flavors_forwards_flavor_id_for_exact_lookup(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.flavors = [
        _flavor("s6.small.1", "1", 1024),
        _flavor("x1.1u.1g", "1", 1024, disk=0),
    ]

    result = await service.list_flavors(flavor_id="x1.1u.1g")

    # The filter goes to the client (server-side request param), not in-memory.
    assert fake_client.calls == [("list_flavors", {"flavor_id": "x1.1u.1g"})]
    assert result["total"] == 1
    assert result["items"][0]["id"] == "x1.1u.1g"

    missing = await service.list_flavors(flavor_id="no-such-flavor")
    assert missing["total"] == 0


# -------------------------------------------------------------------- keypairs


async def test_list_keypairs_flattens_nova_nested_shape(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.keypairs = [
        {
            "keypair": {
                "name": "kp-1",
                "fingerprint": "fa:16:3e:aa",
                "type": "ssh",
                "public_key": "<omitted-public-key>",
            }
        }
    ]

    result = await service.list_keypairs()

    assert result["total"] == 1
    # The nested "keypair" wrapper is unwrapped and public_key dropped.
    assert result["items"] == [{"name": "kp-1", "fingerprint": "fa:16:3e:aa", "type": "ssh"}]


async def test_list_keypairs_accepts_flat_entries(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.keypairs = [{"name": "kp-flat", "fingerprint": "aa:bb", "type": "ssh"}]

    result = await service.list_keypairs()

    assert result["items"] == [{"name": "kp-flat", "fingerprint": "aa:bb", "type": "ssh"}]


async def test_list_keypairs_limit_caps_returned_not_total(
    fake_client: FakeLifecycleClient, service: EcsLifecycleService
) -> None:
    fake_client.keypairs = [
        {"keypair": {"name": "kp-1", "fingerprint": "aa", "type": "ssh"}},
        {"keypair": {"name": "kp-2", "fingerprint": "bb", "type": "ssh"}},
    ]

    result = await service.list_keypairs(limit=1)

    assert result["total"] == 2
    assert result["count"] == 1
