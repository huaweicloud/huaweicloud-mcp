# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Tests for the ECS traffic-protection layer (call_sdk).

These tests exercise the two layers ``call_sdk`` adds over ``asyncio.to_thread``:
the semaphore that caps concurrency, and the retry-with-backoff that absorbs a
transient 429/5xx. The SDK exception types are imported with ``importorskip``
so the suite runs in environments where the SDK is not installed; the
concurrency and success-path tests run without the SDK at all.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from huaweicloud_mcp_core.errors import McpToolError

from mcp_huaweicloud_ecs_common import throttle
from mcp_huaweicloud_ecs_common.throttle import (
    _backoff_delay,
    _get_semaphore,
    _is_retryable,
    call_sdk,
)


@pytest.fixture(autouse=True)
def _reset_semaphore() -> None:
    """Reset the module-level semaphore between tests.

    The semaphore is a process-wide singleton built on first use and then locked
    in (see _get_semaphore). Tests that drive the env-var read need a clean
    slate or the first test to build it pins the value for the rest. The guard
    lock is reset too, so a test that runs under its own loop (the cross-loop
    test) always exercises the lazy-build path rather than a lock bound to a
    loop some earlier async test closed.
    """
    throttle._semaphore = None
    throttle._semaphore_lock = None
    yield
    throttle._semaphore = None
    throttle._semaphore_lock = None


@pytest.fixture(autouse=True)
def _zero_backoff(monkeypatch) -> None:
    """Pin the backoff schedule to all-zeros so retry tests don't sleep 5s.

    The real schedule (5s/10s/20s) exists to give APIG's quota room to recover;
    in tests a real 5s sleep only slows the suite. Patched to zero, the retry
    still fires (attempt advances, the call runs a second time) without the
    wall-clock cost. Tests that assert on the schedule itself re-patch after
    this fixture.
    """
    monkeypatch.setattr(throttle, "_BACKOFF_SECONDS", (0.0, 0.0, 0.0))


# --- success path ----------------------------------------------------------


async def test_call_sdk_returns_result() -> None:
    """A plain call passes through and returns the function's result."""

    def _call() -> dict[str, int]:
        return {"value": 42}

    result = await call_sdk(_call)
    assert result == {"value": 42}


# --- concurrency cap -------------------------------------------------------


async def test_semaphore_caps_concurrency(monkeypatch) -> None:
    """No more than ``max_concurrent`` calls run at the same instant."""
    monkeypatch.setenv("HUAWEICLOUD_MCP_MAX_CONCURRENT", "3")
    in_flight = 0
    peak = 0
    lock = threading.Lock()  # _call runs in a thread, so use a real lock

    def _call() -> int:
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        # Hold the slot long enough for other tasks to pile up at the semaphore.
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return 1

    tasks = [call_sdk(_call) for _ in range(10)]
    await asyncio.gather(*tasks)
    assert peak <= 3


# --- retryable classification ---------------------------------------------


def test_is_retryable_429_and_5xx() -> None:
    """429 and 5xx are retryable; 4xx (except 429) are not."""
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    for code in (429, 500, 502, 503):
        exc = ServiceResponseException.__new__(ServiceResponseException)
        exc.status_code = code
        assert _is_retryable(exc), f"{code} should be retryable"

    for code in (400, 401, 403, 404):
        exc = ServiceResponseException.__new__(ServiceResponseException)
        exc.status_code = code
        assert not _is_retryable(exc), f"{code} should NOT be retryable"


# --- backoff math ---------------------------------------------------------


def test_backoff_follows_fixed_schedule(monkeypatch) -> None:
    """Fixed schedule 5s/10s/20s for attempts 0/1/2, before jitter.

    Re-patches _BACKOFF_SECONDS back to the real schedule: the autouse
    _zero_backoff fixture zeroes it so retry tests don't sleep 5s, but this
    test asserts the real schedule, so it restores it.
    """
    monkeypatch.setattr(throttle, "_BACKOFF_SECONDS", (5.0, 10.0, 20.0))
    assert _backoff_delay(0, 0.0) == pytest.approx(5.0)
    assert _backoff_delay(1, 0.0) == pytest.approx(10.0)
    assert _backoff_delay(2, 0.0) == pytest.approx(20.0)


def test_backoff_clamps_past_end_of_schedule(monkeypatch) -> None:
    """attempt > len(schedule) reuses the last entry (20s), not IndexError."""
    monkeypatch.setattr(throttle, "_BACKOFF_SECONDS", (5.0, 10.0, 20.0))
    assert _backoff_delay(99, 0.0) == pytest.approx(20.0)


async def test_call_sdk_explicit_max_concurrent_zero_raises() -> None:
    """An explicit max_concurrent=0 raises instead of hanging on Semaphore(0).

    The env-var path is bounded by _env_int, but an explicit caller bypasses
    it; the same bound must be guarded here too, or one bad call hangs every
    call silently.
    """

    def _call() -> str:
        return "ok"

    with pytest.raises(RuntimeError, match="max_concurrent"):
        await call_sdk(_call, max_concurrent=0)


# --- 429 retry success / failure ------------------------------------------


async def test_call_sdk_retries_429_then_succeeds() -> None:
    """One 429 followed by success: call_sdk returns the success result."""
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    calls = 0

    def _call() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 429
            raise exc
        return "ok"

    result = await call_sdk(_call, max_retries=1, retry_jitter=0.0)
    assert result == "ok"
    assert calls == 2


async def test_call_sdk_default_retries_three_times() -> None:
    """The default max_retries is 3: two 429s then success still returns ok.

    Pins the default that changed from 1 to 3 so the 5s/10s/20s schedule is
    fully exercised. A test that only retried once would never reach the 10s
    and 20s schedule entries.
    """
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    calls = 0

    def _call() -> str:
        nonlocal calls
        calls += 1
        if calls <= 2:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 429
            raise exc
        return "ok"

    # No explicit max_retries — exercises the module default (3).
    result = await call_sdk(_call, retry_jitter=0.0)
    assert result == "ok"
    assert calls == 3  # 2 retries after the first failure


async def test_call_sdk_clamps_max_retries_to_schedule_length() -> None:
    """max_retries > len(_BACKOFF_SECONDS) is clamped, never indexes out of range."""
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    calls = 0

    def _call() -> str:
        nonlocal calls
        calls += 1
        if calls <= 2:
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 429
            raise exc
        return "ok"

    # max_retries=99 would overflow the 3-entry schedule; it is clamped to 3.
    result = await call_sdk(_call, max_retries=99, retry_jitter=0.0)
    assert result == "ok"
    assert calls == 3


async def test_call_sdk_429_after_retry_fails_with_rate_limited() -> None:
    """Sustained 429 surfaces as MCP_RATE_LIMITED, not a bare HTTP_429."""
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    def _call() -> str:
        exc = ServiceResponseException.__new__(ServiceResponseException)
        exc.status_code = 429
        exc.request_id = "req-7"
        raise exc

    with pytest.raises(McpToolError) as excinfo:
        await call_sdk(_call, max_retries=1, retry_jitter=0.0)
    err = excinfo.value
    assert err.code == "MCP_RATE_LIMITED"
    assert err.request_id == "req-7"
    # The hint must tell the Agent not to retry at once — that is the whole point
    # of surfacing this code distinctly from a bare 429.
    assert "not" in err.hint.lower() and "retry" in err.hint.lower()


async def test_call_sdk_5xx_after_retry_fails_with_server_error() -> None:
    """Sustained 5xx surfaces as MCP_SERVER_ERROR."""
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    def _call() -> str:
        exc = ServiceResponseException.__new__(ServiceResponseException)
        exc.status_code = 503
        raise exc

    with pytest.raises(McpToolError) as excinfo:
        await call_sdk(_call, max_retries=1, retry_jitter=0.0)
    assert excinfo.value.code == "MCP_SERVER_ERROR"


async def test_call_sdk_connection_error_after_retry_fails_with_transient() -> None:
    """Sustained ConnectionError surfaces as MCP_TRANSIENT_ERROR with a slow-down hint.

    The hint is the whole point for transport failures too: without it the Agent
    sees a bare MCP_SDK_ERROR and re-sends at once — the avalanche this layer
    exists to stop. The hint must tell the Agent not to retry at once.
    """

    def _call() -> str:
        raise ConnectionError("reset by peer")

    with pytest.raises(McpToolError) as excinfo:
        await call_sdk(_call, max_retries=1, retry_jitter=0.0)
    err = excinfo.value
    assert err.code == "MCP_TRANSIENT_ERROR"
    assert "not" in err.hint.lower() and "retry" in err.hint.lower()


async def test_call_sdk_retries_requests_connection_error_then_succeeds() -> None:
    """A real requests.exceptions.ConnectionError is retried and can succeed.

    The SDK's HTTP layer is ``requests``, so this is the exception a real network
    blip raises — and it is NOT a subclass of the builtin ConnectionError (it
    subclasses RequestException). The test pins that the retry layer matches the
    real exception, not just the builtin a naive implementation would catch.
    """
    requests = pytest.importorskip("requests")
    calls = 0

    def _call() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise requests.exceptions.ConnectionError("connection reset")
        return "ok"

    result = await call_sdk(_call, max_retries=1, retry_jitter=0.0)
    assert result == "ok"
    assert calls == 2


async def test_call_sdk_retries_requests_read_timeout_then_succeeds() -> None:
    """A real requests.exceptions.ReadTimeout is retried too.

    ReadTimeout is not a subclass of builtin TimeoutError (it subclasses
    RequestException → OSError); matching only the builtin would miss it.
    """
    requests = pytest.importorskip("requests")
    calls = 0

    def _call() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise requests.exceptions.ReadTimeout("read timed out")
        return "ok"

    result = await call_sdk(_call, max_retries=1, retry_jitter=0.0)
    assert result == "ok"
    assert calls == 2


async def test_call_sdk_requests_timeout_after_retry_fails_with_transient() -> None:
    """Sustained requests.exceptions.Timeout surfaces as MCP_TRANSIENT_ERROR."""
    requests = pytest.importorskip("requests")

    def _call() -> str:
        raise requests.exceptions.Timeout("timed out")

    with pytest.raises(McpToolError) as excinfo:
        await call_sdk(_call, max_retries=1, retry_jitter=0.0)
    assert excinfo.value.code == "MCP_TRANSIENT_ERROR"


# --- non-retryable fast fail ----------------------------------------------


async def test_call_sdk_4xx_fails_fast() -> None:
    """401 is not retried: call_sdk raises immediately, no sleep."""
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    calls = 0

    def _call() -> str:
        nonlocal calls
        calls += 1
        exc = ServiceResponseException.__new__(ServiceResponseException)
        exc.status_code = 401
        exc.error_code = "Common.0203"
        exc.error_msg = "unauthorized"
        exc.request_id = "req-1"
        raise exc

    with pytest.raises(McpToolError) as excinfo:
        await call_sdk(_call, max_retries=5, retry_jitter=0.0)
    # 401 wraps as the SDK's error_code, and we only called once (no retry).
    assert excinfo.value.code == "Common.0203"
    assert calls == 1


async def test_call_sdk_generic_exception_fails_fast() -> None:
    """A ValueError is wrapped as MCP_SDK_ERROR with no retry."""
    calls = 0

    def _call() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("config error")

    with pytest.raises(McpToolError) as excinfo:
        await call_sdk(_call, max_retries=5, retry_jitter=0.0)
    assert excinfo.value.code == "MCP_SDK_ERROR"
    assert calls == 1


# --- McpToolError passthrough ---------------------------------------------


async def test_call_sdk_passes_through_mcp_tool_error() -> None:
    """A business McpToolError (e.g. MCP_NOT_FOUND) is not retried or re-wrapped."""

    def _call() -> str:
        raise McpToolError("MCP_NOT_FOUND", "server gone")

    with pytest.raises(McpToolError) as excinfo:
        await call_sdk(_call, max_retries=3, retry_jitter=0.0)
    assert excinfo.value.code == "MCP_NOT_FOUND"


# --- semaphore memoization -----------------------------------------------


async def test_semaphore_is_built_once_and_locked_in(monkeypatch) -> None:
    """The semaphore is built on first use and then locked in for the process.

    The env var is read exactly once; a later change does NOT rebuild the
    semaphore. Rebuilding mid-flight would leave the old semaphore's in-flight
    holders unconstrained by a lowered cap — a window where the protection this
    layer provides is defeated. Locking the value in makes "lower the cap"
    actually lower it (after restart), instead of silently exceeding it.
    """
    monkeypatch.setenv("HUAWEICLOUD_MCP_MAX_CONCURRENT", "4")
    sem_a = await _get_semaphore()
    sem_b = await _get_semaphore()
    assert sem_a is sem_b  # second call reuses, never re-reads env

    # A later change to the env var is deliberately ignored.
    monkeypatch.setenv("HUAWEICLOUD_MCP_MAX_CONCURRENT", "16")
    sem_c = await _get_semaphore()
    assert sem_c is sem_a  # still the same instance — not rebuilt


# --- config bounds: a typo must fail loudly, not silently degrade ----------


@pytest.mark.parametrize(
    "value",
    ["0", "-1", "999"],  # 0 hangs, negative invalid, way past the ceiling
)
async def test_out_of_range_max_concurrent_raises(monkeypatch, value):
    """An out-of-range MAX_CONCURRENT raises at first use, not silently degrades.

    This is the only env-var-backed knob now; the retry parameters are module
    constants (see test_retry_params_not_read_from_env). A non-numeric value
    falls back to the default; a numeric-but-unreasonable value (0, negative,
    huge) is an operator error and must fail loudly so it is seen, not hidden
    as a hung server.
    """
    monkeypatch.setenv("HUAWEICLOUD_MCP_MAX_CONCURRENT", value)

    def _call() -> str:
        return "ok"

    with pytest.raises(RuntimeError, match="HUAWEICLOUD_MCP_MAX_CONCURRENT"):
        await call_sdk(_call)


async def test_non_numeric_max_concurrent_falls_back_to_default(monkeypatch):
    """A non-numeric value is treated as unset, not as an error.

    Only *numeric-but-unreasonable* is an error; garbage like 'abc' still falls
    back to the default, so a stray typo does not take the server down.
    """
    monkeypatch.setenv("HUAWEICLOUD_MCP_MAX_CONCURRENT", "abc")

    def _call() -> str:
        return "ok"

    # No raise — the default is used.
    assert await call_sdk(_call) == "ok"


# --- retry parameters are NOT configurable via env (only MAX_CONCURRENT is) -


@pytest.mark.parametrize(
    "env_set",
    [
        {"HUAWEICLOUD_MCP_MAX_RETRIES": "999"},
        {"HUAWEICLOUD_MCP_RETRY_BASE_SECONDS": "9999"},
        {"HUAWEICLOUD_MCP_RETRY_JITTER_SECONDS": "9999"},
    ],
)
async def test_retry_params_not_read_from_env(monkeypatch, env_set):
    """Setting a retry env var has no effect — it is not a knob anymore.

    These three used to be configurable; a wrong value could silently defeat
    the backoff layer (base=0+jitter=0 = zero-delay retry). They are now module
    constants, so setting the env var must NOT change behavior and must NOT
    raise — the env var is simply ignored. MAX_CONCURRENT is the only knob.
    """
    for k, v in env_set.items():
        monkeypatch.setenv(k, v)

    def _call() -> str:
        return "ok"

    # No raise (the var is ignored), no effect: the call just succeeds.
    assert await call_sdk(_call) == "ok"


# --- network errors are retryable -----------------------------------------


def test_is_retryable_connection_error() -> None:
    """A ConnectionError (transport blip) is retried, not surfaced at once.

    A transient network hiccup is exactly what one retry absorbs; treating it
    as fatal would let a 5-second network blip fail a call that a retry would
    have succeeded.
    """
    assert _is_retryable(ConnectionError("reset by peer"))
    assert _is_retryable(TimeoutError("timed out"))


def test_is_retryable_value_error_is_not() -> None:
    """A plain ValueError is still not retried — it is a config/param error."""
    assert not _is_retryable(ValueError("bad config"))


def test_is_retryable_dns_error_is_not() -> None:
    """A DNS resolution failure (socket.gaierror) is NOT retried.

    A wrong hostname is a configuration error, not a transient blip — retrying
    only delays the real failure report. gaierror is an OSError subclass, so
    this also guards against a too-broad ``isinstance(exc, OSError)`` check.
    """
    import socket

    assert not _is_retryable(socket.gaierror("name or service not known"))


def test_is_retryable_other_oserror_subclasses_are_not() -> None:
    """FileNotFoundError / PermissionError are OSError subclasses but not retryable.

    They signal a local config problem (missing cert, bad file perms), not a
    transport blip. Matching them as retryable would retry a config error.
    """
    assert not _is_retryable(FileNotFoundError("cert.pem"))
    assert not _is_retryable(PermissionError("/etc/cert"))


def test_is_retryable_connection_reset_is() -> None:
    """ConnectionResetError is a ConnectionError subclass → retryable."""
    assert _is_retryable(ConnectionResetError("reset by peer"))


async def test_call_sdk_retries_connection_error_then_succeeds() -> None:
    """One ConnectionError followed by success: call_sdk returns the result.

    This is the end-to-end proof that a transport blip is absorbed by the retry
    layer instead of bubbling up to the Agent (which would re-send at once).
    """
    calls = 0

    def _call() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError(" transient reset")
        return "ok"

    result = await call_sdk(_call, max_retries=1, retry_jitter=0.0)
    assert result == "ok"
    assert calls == 2


# --- retry does NOT hold the semaphore while sleeping ---------------------


async def test_retry_releases_slot_during_backoff(monkeypatch) -> None:
    """While a retried call sleeps on backoff, its slot is free for another call.

    This pins the behavior the docstring describes: retry happens *outside* the
    semaphore slot, so a call sleeping on backoff does not block another call.
    If a future change moves the sleep back inside the slot, this test fails.
    """
    monkeypatch.setenv("HUAWEICLOUD_MCP_MAX_CONCURRENT", "2")

    in_flight = 0
    peak = 0
    lock = threading.Lock()
    started = threading.Event()

    def _call() -> str:
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        started.set()
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        # First call always 429s once so it sleeps on backoff.
        return "ok"

    # Build a call that 429s once then succeeds, alongside calls that just run.
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    state = {"first_done": False}

    def _flaky() -> str:
        nonlocal in_flight, peak
        if not state["first_done"]:
            state["first_done"] = True
            exc = ServiceResponseException.__new__(ServiceResponseException)
            exc.status_code = 429
            raise exc
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.02)
        with lock:
            in_flight -= 1
        return "flaky-ok"

    # One flaky call (will 429, sleep, retry) + several plain calls run together
    # with max_concurrent=2. If the retried call held its slot during sleep,
    # the plain calls would queue and peak would stay at 1 during the sleep.
    tasks = [call_sdk(_flaky, retry_jitter=0.0)]
    tasks += [call_sdk(_call) for _ in range(4)]
    await asyncio.gather(*tasks)
    # peak reached > 1 means a plain call ran *while* the flaky one slept — the
    # slot was released. (peak == 1 would mean the retried call held its slot.)
    assert peak >= 2


# --- retry error wording: 0 / 1 / N retries --------------------------------


def _make_429_exc():
    pytest.importorskip("huaweicloudsdkcore")
    from huaweicloudsdkcore.exceptions.exceptions import ServiceResponseException

    exc = ServiceResponseException.__new__(ServiceResponseException)
    exc.status_code = 429
    exc.request_id = "req-x"
    return exc


def test_retry_wording_zero_retries_disabled() -> None:
    """max_retries=0 → message says 'retries disabled', not 'after 0 retry'."""
    from huaweicloud_mcp_ecs_common.throttle import _retryable_error

    err = _retryable_error(_make_429_exc(), max_retries=0)
    assert "retries disabled" in err.message
    # Must not say the grammatically wrong "after 0 retry".
    assert "after 0" not in err.message


def test_retry_wording_one_retry_singular() -> None:
    """max_retries=1 → 'after 1 retry' (singular)."""
    from huaweicloud_mcp_ecs_common.throttle import _retryable_error

    err = _retryable_error(_make_429_exc(), max_retries=1)
    assert "after 1 retry" in err.message


def test_retry_wording_many_retries_plural() -> None:
    """max_retries=5 → 'after 5 retries' (plural 'retries')."""
    from huaweicloud_mcp_ecs_common.throttle import _retryable_error

    err = _retryable_error(_make_429_exc(), max_retries=5)
    assert "after 5 retries" in err.message


# --- lazy guard lock survives across event loops ---------------------------


def test_call_sdk_works_across_separate_event_loops() -> None:
    """The lazy guard lock lets call_sdk run under two different loops.

    An import-time ``asyncio.Lock()`` would bind to the first loop that touched
    it and break a second ``asyncio.run``. Building the lock lazily inside
    ``_get_semaphore`` (on the loop actually calling us) keeps it correct across
    loops — tests, embedded hosts and notebooks each spin their own.

    This is a sync test on purpose: it calls ``asyncio.run`` twice itself to
    exercise two genuine separate loops (an async test already runs inside one).
    """

    async def _run(tag: str) -> str:
        return await call_sdk(lambda: tag, max_concurrent=2)

    first = asyncio.run(_run("first"))
    second = asyncio.run(_run("second"))
    assert first == "first"
    assert second == "second"
