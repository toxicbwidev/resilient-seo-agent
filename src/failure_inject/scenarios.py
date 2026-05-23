"""Preset failure scenarios, one per demo script.

Each function returns a configured FailureInjector. Demo scripts wrap
their LLM/tool client through the returned injector, then run the
pipeline. Recovery is observed via the event log.

The numbering matches docs/failure-modes.md and demos/scenario-N-*.py.
"""
from __future__ import annotations

from typing import Any, Callable

from .injector import FailureInjector


def scenario_1_rate_limit() -> FailureInjector:
    """Primary model returns 429 on calls 1-2; gateway routes to fallback on call 3."""
    return FailureInjector(plan={1: "rate_limit", 2: "rate_limit"})


def scenario_2_provider_outage() -> FailureInjector:
    """Primary provider is down: first 3 calls return 503. Circuit opens, chain falls back."""
    return FailureInjector(plan={1: "outage", 2: "outage", 3: "outage"})


def scenario_3_slow_response(slow_sec: float = 30.0) -> FailureInjector:
    """Call 1 sleeps past the client timeout. Real call still runs; we just
    delay it. Pipeline must cancel via timeout and try next provider."""
    return FailureInjector(slow_plan={1: slow_sec})


def scenario_4_tool_failure() -> FailureInjector:
    """The pipeline's tool call (call 1 in the tool client) fails with 500.
    Post-tool guardrail / orchestrator detects, enters degraded mode."""
    return FailureInjector(plan={1: "tool_failure"})


def _corrupt_to_garbage(_response: Any) -> str:
    """Replace an LLM response payload with malformed JSON.
    Output guardrail / parser should reject this."""
    return "<<<corrupted-payload-not-json>>>"


def scenario_5_corrupted_response(
    corrupter: Callable[[Any], Any] = _corrupt_to_garbage,
) -> FailureInjector:
    """Call 1 returns successfully but the payload is junk. Caller validates
    the response and rejects → retry (which succeeds on call 2)."""
    return FailureInjector(corrupt_plan={1: corrupter})


def scenario_6_cascading() -> FailureInjector:
    """Three different failure modes hit three pipeline steps in sequence.
    No single recovery saves the run; the orchestrator must persist state
    after each successful step and let a human resume from the checkpoint."""
    return FailureInjector(
        plan={1: "outage", 2: "rate_limit", 3: "timeout"},
    )
