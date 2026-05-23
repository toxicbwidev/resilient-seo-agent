"""Scenario 5 — the model returns content but the payload is junk.

The injector replaces the response body with a malformed string. The
pipeline's parse_output (which calls extract_json for most steps)
detects the malformed payload and raises ValueError. The retry path
then succeeds with the untouched second call.

In production this matches the case where an output guardrail or a
schema validator rejects the model's response and the agent re-prompts.
"""
from _common import run_scenario

from src.failure_inject import scenarios

if __name__ == "__main__":
    run_scenario(
        title="Scenario 5 — corrupted/malformed model response",
        scenario_slug="scenario-5-corrupted-response",
        injector=scenarios.scenario_5_corrupted_response(),
    )
