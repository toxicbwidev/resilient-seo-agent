"""Exception hierarchy for injected failures.

Distinguishing injected failures from real ones matters during a demo: we
want to log "this was injected at call N to demonstrate scenario X", not
"the agent recovered from an unexpected outage we caused by accident."
Every injected exception carries a `scenario_name` so the recovery
orchestrator can log it accurately.
"""
from __future__ import annotations


class InjectedFailure(Exception):
    """Sentinel base. Pipeline catches `InjectedFailure` separately from real
    provider errors when emitting demo telemetry."""

    scenario_name: str = "unknown"
    http_status: int = 0


class InjectedRateLimit(InjectedFailure):
    scenario_name = "rate_limit"
    http_status = 429


class InjectedOutage(InjectedFailure):
    scenario_name = "provider_outage"
    http_status = 503


class InjectedTimeout(InjectedFailure):
    scenario_name = "slow_response"
    http_status = 0  # client-side timeout, no HTTP response


class InjectedToolFailure(InjectedFailure):
    scenario_name = "tool_failure"
    http_status = 500


class InjectedCorrupted(InjectedFailure):
    """Used as a marker; actual corruption is applied via a transform, not
    by raising. This class exists so demo logging is uniform."""

    scenario_name = "corrupted_response"
    http_status = 200  # the network call succeeded, the payload is junk
