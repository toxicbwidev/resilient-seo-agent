"""FailureInjector — middleware that wraps any callable and injects
deterministic failures on specific call indices.

Why deterministic? A demo with random failures is unconvincing — judges
can't tell whether the agent recovered or whether the failure simply
didn't happen this run. With a plan keyed on call index, scenario N
always fails at the same call, every time.

Three injection modes:

  - raise:   replace the call with raising one of the InjectedFailure
             subclasses. The real callable is never invoked.
  - slow:    sleep before the real call so a client-side timeout fires.
             The real callable is still invoked (and may itself succeed).
  - corrupt: invoke the real callable, then mutate its return value.
             Demonstrates "the model responded but the output is bad."

A single injector can mix all three modes — call 1 slow, call 2 raises
rate_limit, call 3 corrupts. That's how scenario-6 (cascading) is built.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .exceptions import (
    InjectedFailure,
    InjectedOutage,
    InjectedRateLimit,
    InjectedTimeout,
    InjectedToolFailure,
)

SCENARIO_TO_EXC: dict[str, type[InjectedFailure]] = {
    "rate_limit": InjectedRateLimit,
    "outage": InjectedOutage,
    "timeout": InjectedTimeout,
    "tool_failure": InjectedToolFailure,
}


class FailureInjector:
    def __init__(
        self,
        plan: dict[int, str] | None = None,
        slow_plan: dict[int, float] | None = None,
        corrupt_plan: dict[int, Callable[[Any], Any]] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.plan = plan or {}
        self.slow_plan = slow_plan or {}
        self.corrupt_plan = corrupt_plan or {}
        self.sleep_fn = sleep_fn  # overridable for fast tests
        self.call_count = 0
        self.injections_fired: list[dict[str, Any]] = []

        bad = set(self.plan.values()) - set(SCENARIO_TO_EXC)
        if bad:
            raise ValueError(
                f"Unknown injection scenarios: {sorted(bad)}. "
                f"Allowed: {sorted(SCENARIO_TO_EXC)}"
            )

    def reset(self) -> None:
        self.call_count = 0
        self.injections_fired.clear()

    def wrap(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Return a wrapped callable that applies this injector per invocation."""

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self.call_count += 1
            idx = self.call_count

            if idx in self.slow_plan:
                delay = self.slow_plan[idx]
                self.injections_fired.append(
                    {"call": idx, "type": "slow", "delay_sec": delay}
                )
                self.sleep_fn(delay)

            if idx in self.plan:
                scenario = self.plan[idx]
                exc_cls = SCENARIO_TO_EXC[scenario]
                self.injections_fired.append({"call": idx, "type": scenario})
                raise exc_cls(f"Injected at call {idx}: {scenario}")

            result = fn(*args, **kwargs)

            if idx in self.corrupt_plan:
                self.injections_fired.append({"call": idx, "type": "corrupt"})
                result = self.corrupt_plan[idx](result)

            return result

        return wrapped
