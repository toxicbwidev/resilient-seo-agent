"""Scenario 6 — three different failure modes hit three steps in sequence.

Call 1 fails with outage, call 2 with rate_limit, call 3 with timeout —
all in the first pipeline step. With max_retries_per_step=2, the budget
covers calls 1..3 for the voice step. All three fail; the pipeline
aborts on call 3, **state is preserved on disk** (zero completed steps),
and the operator can resume later.

This is the demo that proves the state-preservation layer's value: no
recovery mechanism inside a single step saves the run, but the agent
also doesn't lose work or end up in an undefined state.
"""
from _common import run_scenario

from src.failure_inject import scenarios

if __name__ == "__main__":
    run_scenario(
        title="Scenario 6 — cascading failures (outage → rate_limit → timeout)",
        scenario_slug="scenario-6-cascading",
        injector=scenarios.scenario_6_cascading(),
        expect_abort=True,
    )
