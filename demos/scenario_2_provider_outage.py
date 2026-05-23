"""Scenario 2 — primary provider is down. Three consecutive 5xx errors.

With max_retries_per_step=2, the first step (voice) gets calls 1, 2, 3 —
all fail with InjectedOutage — and the pipeline aborts on the third
attempt. The point of this demo isn't that the agent recovers (it
doesn't, in this configuration). The point is that **state is preserved
on disk** so a later run with the same pipeline_id can resume from
exactly the right step once the provider is back.
"""
from _common import run_scenario

from src.failure_inject import scenarios

if __name__ == "__main__":
    run_scenario(
        title="Scenario 2 — primary provider outage (three consecutive 5xx)",
        scenario_slug="scenario-2-provider-outage",
        injector=scenarios.scenario_2_provider_outage(),
        expect_abort=True,
    )
