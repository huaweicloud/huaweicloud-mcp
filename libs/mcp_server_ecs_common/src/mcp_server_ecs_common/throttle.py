# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: MIT

"""Traffic protection for ECS SDK calls: bounded concurrency + retry with backoff.

Both ECS MCP servers (``mcp_server_ecs`` and ``mcp_server_ecs_lifecycle``) share
one AK/SK (one Huawei Cloud user), so they share one APIG per-user rate-limit
budget. Two failure modes would otherwise overrun that budget:

* **burst** — the Agent fires many independent tool calls at once and they all
  reach APIG in the same instant, tripping the per-user QPS cap.
* **avalanche** — APIG returns 429 (or the backend 5xx) and the MCP server
  surfaces it as a plain error; the Agent's reflex is to retry at once, which
  trips the cap again and again.

``call_sdk`` sits where ``asyncio.to_thread`` sat in every client method. It
adds two layers that ``asyncio.to_thread`` does not:

1. A process-wide semaphore caps how many SDK calls run at once. The cap is
   read from ``HUAWEICLOUD_MCP_MAX_CONCURRENT`` (default 20); callers that
   exceed it wait at the semaphore, so the request never reaches APIG. This is
   the *only* knob exposed to the operator — the retry parameters below are
   internal and not configurable, since a wrong value can silently defeat the
   layer and the operator has no better judgment on them than the tuned
   defaults.
2. Retryable responses (429 / 5xx) are retried up to three times with backoff
   before the error is surfaced. Sustained 429 means the quota is genuinely
   exhausted, so the retries absorb a transient blip; if all three retries
   fail the Agent receives ``MCP_RATE_LIMITED`` with a hint that says *do not
   retry at once*, not a bare ``HTTP_429`` it would reflexively re-send.
   Transient transport failures (the SDK's ``requests`` layer: connection
   resets, timeouts) get the same treatment: retried up to three times, then
   surfaced as ``MCP_TRANSIENT_ERROR`` with the same slow-down hint — without
   it the Agent would re-send at once and turn a 5-second network blip into an
   avalanche. The backoff schedule is a fixed sequence — 5s, 10s, 20s — rather
   than a blind exponential; the first retry at 5s gives APIG's per-user quota
   a meaningful window to recover, and the fixed cadence is recognizable in
   logs when a 429 storm is in progress.

The semaphore is per-process: it bounds only the calls made through this one
process. When the two ECS servers run as separate processes they each keep
their own semaphore, so the combined load on APIG is the sum — the ``20`` default
is a *per-process* cap, not a global one; in that deployment APIG's own
per-user throttle is the global backstop, and the retry layer here keeps a 429
from cascading into an avalanche regardless of how many processes are involved.

The semaphore value is read from the environment ONCE, on first use, and then
locked in for the life of the process. Reading it every call and rebuilding the
semaphore on a change would leave the old semaphore's in-flight holders
unconstrained by a lowered cap — a brief window where the protection this layer
provides is defeated. Treating it as a startup-time setting makes "lower the cap"
actually lower it (after restart), instead of silently exceeding it for a beat.
Change the value, then restart.
"""

from __future__ import annotations

import asyncio
import os
import random
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # McpToolError is imported lazily at runtime inside _retryable_error and
    # call_sdk to avoid a hard runtime dep on huaweicloud_mcp_core at module
    # import; this is only for the type checker to resolve the annotations.
    from huaweicloud_mcp_core.errors import McpToolError

# Concurrency is the one knob exposed to the operator: it depends on the
# deployment (how many server processes run, the APIG per-user quota) and the
# operator is the only one with that information. Bounds guard the env read —
# a typo (``MAX_CONCURRENT=0``) used to make the server silently hang.
_CONCURRENT_FLOOR, _CONCURRENT_CEIL = 1, 64
_DEFAULT_MAX_CONCURRENT = 20

# Retry parameters are NOT exposed as environment variables. They are internal
# to the backoff algorithm, and an operator has no better judgment on them
# than these tuned defaults — but a wrong value can quietly defeat the layer
# (base=0+jitter=0 = zero-delay retry = the Agent avalanche it absorbs). Keeping
# them as constants removes three "set it wrong and break protection" foot-guns
# while still letting tests override them via explicit ``call_sdk`` arguments.
#
# The backoff schedule is a fixed sequence — 5s, 10s, 20s — rather than
# ``base * 2**attempt``. The fixed schedule makes the wait times predictable
# for an operator watching logs (a 429 storm shows a recognizable 5/10/20
# cadence, not an opaque exponential), and the first retry at 5s gives APIG's
# per-user quota a meaningful window to recover instead of hammering it again
# in half a second. ``_MAX_RETRIES`` is capped at ``len(_BACKOFF_SECONDS)`` so
# the schedule never indexes out of range. With ``_MAX_RETRIES = 3`` each of the
# three schedule entries is used exactly once: 5s before retry 1, 10s before
# retry 2, 20s before retry 3, then fail.
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (5.0, 10.0, 20.0)
_RETRY_JITTER = 0.25

# The transport exception types to treat as transient. huaweicloudsdkcore uses
# ``requests`` under the hood, so a real network blip surfaces as
# ``requests.exceptions.*``, NOT Python's built-in ``ConnectionError``/
# ``TimeoutError`` — the ``requests`` ones subclass ``RequestException``, not
# the builtins, so matching only the builtins caught none of the real errors
# and network-retry silently never fired. The tuple is extended lazily on
# first use (requests is a hard dep of the SDK, so it's present whenever the
# SDK is — but we degrade to builtins if it somehow is not, not crash).
_TRANSIENT_NETWORK_EXCS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
)


def _transient_network_exceptions() -> tuple[type[BaseException], ...]:
    """Return the transport exception types to treat as transient.

    Lazily extends the builtin tuple with ``requests.exceptions`` types so the
    import is not paid at module load. ``ConnectionError`` (refused/reset/
    aborted) and ``Timeout`` (connect or read) qualify; ``HTTPError`` does not
    (it is a structured response, handled via :class:`ServiceResponseException`
    above) and ``RequestException`` is too broad (includes 4xx).
    """
    try:
        import requests.exceptions as _re
    except ImportError:
        return _TRANSIENT_NETWORK_EXCS
    return (*_TRANSIENT_NETWORK_EXCS, _re.ConnectionError, _re.Timeout)


def _env_int(name: str, default: int, floor: int, ceil: int) -> int:
    """Read an int env var; non-numeric falls back to default, out-of-range raises.

    A non-numeric value (``"abc"``, ``""``) is treated as unset and uses the
    default — a stray typo should not take the server down. A numeric-but-
    unreasonable value (``0`` concurrent) is an operator error and raises at
    first use so it is seen, not hidden as a hung server.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    if value < floor or value > ceil:
        raise RuntimeError(
            f"{name}={value!r} is out of range [{floor}, {ceil}]; "
            f"set it within that range or unset it to use the default {default}."
        )
    return value


# A module-level semaphore cannot be constructed at import time: asyncio requires
# a running event loop to exist, and module import happens before the server's
# loop starts. It is created lazily on first use and memoized so every caller in
# the process shares one instance.
#
# The value is read from the environment ONCE, on first use, and locked in. This
# is deliberate: rebuilding the semaphore mid-flight when the env var changes
# leaves the old semaphore's in-flight holders unconstrained by the new (smaller)
# cap — a brief window where the very protection this layer provides is defeated.
# Treating it as a startup-time setting makes "lower the cap" actually lower the
# cap, instead of silently exceeding it for a beat. Change the value, then
# restart.
#
# The guard lock is also lazy: an ``asyncio.Lock()`` built at import time would
# bind to whatever loop happened to run first, breaking reuse across loops
# (tests, embedded hosts, notebook sessions each spin their own). Building it
# on first use inside ``_get_semaphore`` keeps it bound to the loop that
# actually calls us, which is the loop the semaphore lives on too. The steady-
# state read (semaphore already built) is lock-free via double-checked locking;
# the lock is only taken on the first-ever call.
_semaphore: asyncio.Semaphore | None = None
_semaphore_lock: asyncio.Lock | None = None


async def _get_semaphore() -> asyncio.Semaphore:
    """Return the process-wide semaphore, building it on first use.

    The value is resolved from ``HUAWEICLOUD_MCP_MAX_CONCURRENT`` exactly once —
    on the first call — and is never re-read. A mid-flight change to the env
    var is deliberately ignored (see the module-level note): rebuilding under
    in-flight holders would briefly exceed a lowered cap.
    """
    global _semaphore, _semaphore_lock
    # Steady state: already built. No lock, no env read.
    if _semaphore is not None:
        return _semaphore
    if _semaphore_lock is None:
        _semaphore_lock = asyncio.Lock()
    async with _semaphore_lock:
        if _semaphore is None:
            _semaphore = asyncio.Semaphore(
                _env_int(
                    "HUAWEICLOUD_MCP_MAX_CONCURRENT", _DEFAULT_MAX_CONCURRENT,
                    _CONCURRENT_FLOOR, _CONCURRENT_CEIL,
                )
            )
    return _semaphore


def _is_retryable(exc: Exception) -> bool:
    """429 and 5xx are transient; everything else fails fast.

    Network errors raised by ``requests``/the SDK's HTTP layer (timeouts, TLS
    failures, connection resets) are also transient — a blip that resolves in
    seconds is exactly what one retry is for. The transport types matched are
    the ones the SDK actually raises (``requests.exceptions.ConnectionError``
    and ``Timeout``), plus the builtins as a fallback.

    ``OSError`` is deliberately NOT matched wholesale even though the transport
    errors above are its subclasses. ``socket.gaierror`` (DNS resolution
    failure), ``FileNotFoundError`` and ``PermissionError`` are also ``OSError``
    subclasses, but they signal a *configuration* error (wrong hostname, missing
    certificate, bad file perms), not a blip — retrying only delays the real
    failure report. Matching ``OSError`` would silently retry every one of them.
    """
    try:
        from huaweicloudsdkcore.exceptions.exceptions import (  # type: ignore[import-untyped]
            ServiceResponseException,
        )
    except ImportError:
        pass
    else:
        if isinstance(exc, ServiceResponseException):
            return bool(exc.status_code == 429 or exc.status_code >= 500)
    # Transport blips: the endpoint is right, the transport hiccuped. Match the
    # real requests exceptions the SDK raises, not just the builtins.
    return bool(isinstance(exc, _transient_network_exceptions()))


def _backoff_delay(attempt: int, jitter: float) -> float:
    """Fixed-schedule backoff: 5s, 10s, 20s for attempts 0/1/2, plus uniform jitter.

    The schedule is a fixed tuple rather than ``base * 2**attempt`` so the wait
    is predictable for an operator watching logs (a 429 storm shows a
    recognizable 5/10/20 cadence). ``attempt`` is clamped to the last entry so
    a caller that somehow exceeds the schedule still gets the longest wait
    rather than an IndexError. Jitter de-synchronizes concurrent retries that
    all hit 429 in the same instant; without it, N callers sleep the same
    duration and all retry at once, tripping the cap again.
    """
    delay = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
    return float(delay + random.random() * jitter)


def _retryable_error(exc: Exception, max_retries: int) -> McpToolError:
    """Wrap a retryable failure that did not recover as an actionable error.

    The Agent sees ``MCP_RATE_LIMITED`` (429), ``MCP_SERVER_ERROR`` (5xx) or
    ``MCP_TRANSIENT_ERROR`` (transport blip) with a hint that says *slow down*,
    not a bare ``HTTP_429`` / ``MCP_SDK_ERROR`` it would re-send at once. The
    hint is the whole point for non-SDK errors too: without it the Agent's
    reflex on a transient network failure is to retry at once, which is the
    avalanche this layer exists to stop.
    """
    from huaweicloud_mcp_core.errors import McpToolError, wrap_sdk_error

    # "after N retries" / "after 1 retry" / "retries disabled" — wording must
    # stay correct for max_retries=0 (no retries attempted) and !=1 alike.
    if max_retries == 0:
        _attempt_suffix = "retries disabled"
    elif max_retries == 1:
        _attempt_suffix = "after 1 retry"
    else:
        _attempt_suffix = f"after {max_retries} retries"

    is_transport = isinstance(exc, _transient_network_exceptions())

    try:
        from huaweicloudsdkcore.exceptions.exceptions import (
            ServiceResponseException,
        )
    except ImportError:
        pass
    else:
        if isinstance(exc, ServiceResponseException):
            if exc.status_code == 429:
                return McpToolError(
                    code="MCP_RATE_LIMITED",
                    message=(
                        f"APIG rate-limited the request (429) {_attempt_suffix}; "
                        f"the per-user quota is saturated."
                    ),
                    request_id=getattr(exc, "request_id", None),
                    hint=(
                        "This is a throttle, not a parameter error — do not change the "
                        "arguments and retry. Lower the call rate and retry after a pause; "
                        "if it persists, ask the operator to raise the APIG per-user quota."
                    ),
                )
            return McpToolError(
                code="MCP_SERVER_ERROR",
                message=f"Backend returned HTTP {exc.status_code} {_attempt_suffix}.",
                request_id=getattr(exc, "request_id", None),
                hint=(
                    "The cloud service returned a transient server error. Retry after a "
                    "short pause; if it persists, the service may be degraded."
                ),
            )

    if is_transport:
        return McpToolError(
            code="MCP_TRANSIENT_ERROR",
            message=f"Transport failure ({type(exc).__name__}) {_attempt_suffix}.",
            hint=(
                "This is a transient transport failure, not a parameter error — do not "
                "change the arguments and retry at once. Wait a moment and retry; if it "
                "persists, the network path to the cloud service may be degraded."
            ),
        )
    return wrap_sdk_error(exc)


async def call_sdk(
    fn: Callable[..., Any],
    /,
    *args: Any,
    max_concurrent: int | None = None,
    max_retries: int | None = None,
    retry_jitter: float | None = None,
    **kwargs: Any,
) -> Any:
    """Run a synchronous SDK call with bounded concurrency and retry.

    Drop-in replacement for ``await asyncio.to_thread(fn, *args, **kwargs)``:
    every client method that previously wrote that now writes
    ``await call_sdk(_call)`` instead. ``_call`` is the zero-arg closure each
    method already builds; positional/keyword passthrough keeps it working.

    The concurrency cap is read from ``HUAWEICLOUD_MCP_MAX_CONCURRENT`` exactly
    once, on first use, and locked in for the life of the process (see
    :func:`_get_semaphore`). ``max_concurrent`` is accepted only so an explicit
    out-of-range value (e.g. ``0``) fails loudly instead of silently building a
    ``Semaphore(0)`` that hangs every call; in production it is always ``None``
    and the env var decides. The retry parameters (``max_retries``/
    ``retry_jitter``) default to module constants and are only overridden via
    explicit arguments — in tests — since a wrong value can silently defeat the
    backoff layer. Passing explicit retry values in production code is not
    supported.

    The semaphore bounds how many calls are *in flight* to the cloud at once.
    Retry happens *outside* the semaphore slot: a call that hits a transient
    429/5xx releases its slot, sleeps on backoff (so other calls proceed), then
    re-acquires a slot to retry. This keeps throughput up while a retry sleeps,
    but means an extreme-sustained 429 can starve retries — mitigated by the
    retry cap, after which the caller gets ``MCP_RATE_LIMITED`` and stops.
    """
    from huaweicloud_mcp_core.errors import McpToolError, wrap_sdk_error

    if max_concurrent is not None and (
        max_concurrent < _CONCURRENT_FLOOR or max_concurrent > _CONCURRENT_CEIL
    ):
        # An explicit caller (tests, or a programmatic integrator) bypassed
        # _env_int; guard the same bounds here too, so max_concurrent=0 does not
        # build a Semaphore(0) and hang every call silently.
        raise RuntimeError(
            f"max_concurrent={max_concurrent!r} is out of range "
            f"[{_CONCURRENT_FLOOR}, {_CONCURRENT_CEIL}]."
        )
    if max_retries is None:
        max_retries = _MAX_RETRIES
    # ``max_retries`` is clamped to the backoff schedule length so a caller that
    # asks for more retries than the schedule has entries cannot index out of
    # range — it just reuses the longest wait (the last entry) for the extra
    # attempts. ``_MAX_RETRIES`` is already within bounds; this only matters for
    # an explicit ``max_retries`` passed in tests.
    if max_retries > len(_BACKOFF_SECONDS):
        max_retries = len(_BACKOFF_SECONDS)
    if retry_jitter is None:
        retry_jitter = _RETRY_JITTER

    sem = await _get_semaphore()
    attempt = 0
    while True:
        try:
            async with sem:
                return await asyncio.to_thread(fn, *args, **kwargs)
        except McpToolError:
            raise
        except Exception as exc:
            if not _is_retryable(exc) or attempt >= max_retries:
                if _is_retryable(exc):
                    raise _retryable_error(exc, max_retries) from exc
                raise wrap_sdk_error(exc) from exc

            # Transient failure: release the slot, back off, then re-acquire a
            # slot to retry. Other calls proceed during the sleep.
            delay = _backoff_delay(attempt, retry_jitter)
            await asyncio.sleep(delay)
            attempt += 1
