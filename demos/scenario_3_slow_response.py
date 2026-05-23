"""Scenario 3 — primary model responds slowly (simulated client-side delay).

In production, a slow response triggers a TrueFoundry-level timeout and
the gateway routes the retry to the next provider. Here we inject a
short sleep (1 ms in this demo, 30 s in production) before the call and
record it as a "slow" event in the injector log — the same event a real
gateway timeout would emit.
"""
from _common import run_scenario

from src.failure_inject import scenarios

if __name__ == "__main__":
    # 1 ms delay — keep the demo fast. Real-world value would be > timeout.
    run_scenario(
        title="Scenario 3 — slow response from primary model",
        scenario_slug="scenario-3-slow-response",
        injector=scenarios.scenario_3_slow_response(slow_sec=0.001),
    )
