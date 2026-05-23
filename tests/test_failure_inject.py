"""Tests for the failure injection harness.

The harness must be:
  1. Deterministic (same plan → same failure on same call index, every run)
  2. Composable (raise + slow + corrupt can all live in one injector)
  3. Observable (every injection logged in injections_fired)
  4. Inert when no plan is set (passes calls through unchanged)
"""
from __future__ import annotations

import pytest

from src.failure_inject import (
    FailureInjector,
    InjectedOutage,
    InjectedRateLimit,
    InjectedTimeout,
    InjectedToolFailure,
    scenarios,
)


def successful_call(*args, **kwargs) -> str:
    return "ok"


def test_inert_when_no_plan() -> None:
    """No plan → everything passes through."""
    injector = FailureInjector()
    wrapped = injector.wrap(successful_call)

    assert wrapped() == "ok"
    assert wrapped() == "ok"
    assert wrapped() == "ok"
    assert injector.call_count == 3
    assert injector.injections_fired == []


def test_rate_limit_on_specific_calls() -> None:
    injector = FailureInjector(plan={1: "rate_limit", 2: "rate_limit"})
    wrapped = injector.wrap(successful_call)

    with pytest.raises(InjectedRateLimit):
        wrapped()
    with pytest.raises(InjectedRateLimit):
        wrapped()
    assert wrapped() == "ok"  # call 3 passes through
    assert wrapped() == "ok"  # call 4 also passes through

    assert injector.call_count == 4
    assert len(injector.injections_fired) == 2
    assert all(e["type"] == "rate_limit" for e in injector.injections_fired)


def test_outage_then_recovery() -> None:
    injector = FailureInjector(plan={1: "outage", 2: "outage", 3: "outage"})
    wrapped = injector.wrap(successful_call)

    for _ in range(3):
        with pytest.raises(InjectedOutage):
            wrapped()
    assert wrapped() == "ok"
    assert injector.call_count == 4


def test_slow_uses_sleep_fn() -> None:
    """Slow injection uses the injected sleep_fn — no real sleeping in tests."""
    sleeps: list[float] = []
    injector = FailureInjector(
        slow_plan={1: 30.0},
        sleep_fn=sleeps.append,
    )
    wrapped = injector.wrap(successful_call)

    assert wrapped() == "ok"  # slow but doesn't raise
    assert sleeps == [30.0]
    assert injector.injections_fired[0]["type"] == "slow"
    assert injector.injections_fired[0]["delay_sec"] == 30.0


def test_corrupt_modifies_return_value() -> None:
    injector = FailureInjector(corrupt_plan={2: lambda r: r.upper() + "!!!"})
    wrapped = injector.wrap(successful_call)

    assert wrapped() == "ok"          # call 1: unchanged
    assert wrapped() == "OK!!!"       # call 2: corrupted
    assert wrapped() == "ok"          # call 3: unchanged
    assert injector.injections_fired == [{"call": 2, "type": "corrupt"}]


def test_composable_slow_then_raise() -> None:
    """One injector can both sleep and then raise."""
    sleeps: list[float] = []
    injector = FailureInjector(
        plan={1: "timeout"},
        slow_plan={1: 5.0},
        sleep_fn=sleeps.append,
    )
    wrapped = injector.wrap(successful_call)

    with pytest.raises(InjectedTimeout):
        wrapped()
    # slept first, then raised
    assert sleeps == [5.0]
    types = [e["type"] for e in injector.injections_fired]
    assert types == ["slow", "timeout"]


def test_unknown_scenario_rejected_at_init() -> None:
    with pytest.raises(ValueError, match="Unknown injection scenarios"):
        FailureInjector(plan={1: "not-a-real-scenario"})


def test_reset_clears_state() -> None:
    injector = FailureInjector(plan={1: "rate_limit"})
    wrapped = injector.wrap(successful_call)
    with pytest.raises(InjectedRateLimit):
        wrapped()

    injector.reset()
    assert injector.call_count == 0
    assert injector.injections_fired == []
    # after reset, call 1 fails again
    with pytest.raises(InjectedRateLimit):
        wrapped()


def test_scenario_presets_construct_correctly() -> None:
    """Sanity: every preset constructs without error and is a FailureInjector."""
    for fn_name in [
        "scenario_1_rate_limit",
        "scenario_2_provider_outage",
        "scenario_4_tool_failure",
        "scenario_5_corrupted_response",
        "scenario_6_cascading",
    ]:
        injector = getattr(scenarios, fn_name)()
        assert isinstance(injector, FailureInjector)


def test_scenario_3_slow_response_param() -> None:
    """Scenario 3 takes a custom slow_sec parameter."""
    injector = scenarios.scenario_3_slow_response(slow_sec=0.001)
    assert injector.slow_plan == {1: 0.001}


def test_tool_failure_scenario() -> None:
    """Tool failure scenario raises InjectedToolFailure on call 1."""
    injector = scenarios.scenario_4_tool_failure()
    wrapped = injector.wrap(successful_call)
    with pytest.raises(InjectedToolFailure):
        wrapped()


def test_cascading_scenario_fires_three_distinct_failures() -> None:
    injector = scenarios.scenario_6_cascading()
    wrapped = injector.wrap(successful_call)

    with pytest.raises(InjectedOutage):
        wrapped()
    with pytest.raises(InjectedRateLimit):
        wrapped()
    with pytest.raises(InjectedTimeout):
        wrapped()
    assert wrapped() == "ok"  # call 4 passes through

    types = [e["type"] for e in injector.injections_fired]
    assert types == ["outage", "rate_limit", "timeout"]
