"""Scenario 1 — Bedrock returns 429 on the first two calls, the third succeeds.

In production, the TrueFoundry Gateway would catch the 429 and route the
retry to the next model in the priority chain (Claude → Mistral). Here
we simulate the gateway's behaviour locally so the recovery path is
verifiable without a live AWS account.
"""
from _common import run_scenario

from src.failure_inject import scenarios

if __name__ == "__main__":
    run_scenario(
        title="Scenario 1 — primary model returns 429 (rate limit)",
        scenario_slug="scenario-1-rate-limit",
        injector=scenarios.scenario_1_rate_limit(),
    )
