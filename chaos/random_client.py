"""Probability-based failure injection client wrapper.

The existing failure_inject.FailureInjector is plan-based: you say
"fail call 2 with rate_limit, call 4 with outage". That's right for
deterministic demos.

For chaos engineering we need probability-based injection: every call
rolls a die. Each failure type has an independent probability. With a
seed, runs are reproducible — same seed, same sequence of failures.

This is a thin wrapper over the GatewayClient protocol. It records
every injection in injection_log so the runner can correlate observed
pipeline behavior to injected faults.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from src.agent.client import GatewayClient
from src.failure_inject.exceptions import (
    InjectedOutage,
    InjectedRateLimit,
    InjectedToolFailure,
)


@dataclass
class FailureProfile:
    """Probability of each failure type per model call.

    All probabilities are independent rolls — a single call could
    technically trigger multiple, but the wrapper checks in order and
    fires the first hit, so order matters slightly. Sum of probs
    typically 0.10..0.40 for realistic chaos; >0.50 is hostile.
    """

    rate_limit: float = 0.0       # raises InjectedRateLimit
    outage: float = 0.0           # raises InjectedOutage
    slow: float = 0.0             # sleeps `slow_seconds` then returns normally
    tool_failure: float = 0.0     # raises InjectedToolFailure
    corrupted: float = 0.0        # returns malformed JSON (parse fails)
    hallucinate: float = 0.0      # returns valid JSON but empty content
    hang: float = 0.0             # sleeps `hang_seconds` (watchdog catches)
    # Tunables
    slow_seconds: float = 0.05
    hang_seconds: float = 2.0


@dataclass
class InjectionRecord:
    call_index: int
    failure_type: str
    ts: float


class RandomFailureClient:
    """Wraps a GatewayClient; on each call, probabilistically injects
    one failure from the profile. Deterministic given the seed.
    """

    def __init__(
        self,
        underlying: GatewayClient,
        profile: FailureProfile,
        seed: int = 0,
    ) -> None:
        self._real = underlying
        self._profile = profile
        self._rng = random.Random(seed)
        self.injection_log: list[InjectionRecord] = []
        self.call_count = 0

    def complete(self, model_pref: str, system: str, user: str) -> str:
        self.call_count += 1
        idx = self.call_count
        # Roll dice for each failure type in fixed order so seed is reproducible
        # even if profile changes between runs (unrelated profiles share RNG).
        rolls = {ft: self._rng.random() for ft in (
            "rate_limit", "outage", "slow", "tool_failure",
            "corrupted", "hallucinate", "hang",
        )}
        p = self._profile
        if rolls["rate_limit"] < p.rate_limit:
            self._record(idx, "rate_limit")
            raise InjectedRateLimit("chaos: rate limit")
        if rolls["outage"] < p.outage:
            self._record(idx, "outage")
            raise InjectedOutage("chaos: provider outage (503)")
        if rolls["tool_failure"] < p.tool_failure:
            self._record(idx, "tool_failure")
            raise InjectedToolFailure("chaos: tool 5xx")
        if rolls["slow"] < p.slow:
            self._record(idx, "slow")
            time.sleep(p.slow_seconds)
            return self._real.complete(model_pref, system, user)
        if rolls["hang"] < p.hang:
            self._record(idx, "hang")
            time.sleep(p.hang_seconds)
            return self._real.complete(model_pref, system, user)
        if rolls["corrupted"] < p.corrupted:
            self._record(idx, "corrupted")
            return "{not valid json at all"
        if rolls["hallucinate"] < p.hallucinate:
            self._record(idx, "hallucinate")
            # Return valid JSON but with insufficient content (catches
            # via the postcondition layer in self_test.py)
            return "{}"
        return self._real.complete(model_pref, system, user)

    def _record(self, idx: int, ftype: str) -> None:
        self.injection_log.append(
            InjectionRecord(call_index=idx, failure_type=ftype, ts=time.time())
        )
