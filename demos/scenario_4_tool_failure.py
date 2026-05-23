"""Scenario 4 — an MCP tool call fails with 500.

In our pipeline, this is the first LLM call (which conceptually represents
the start of a tool-using step). The pipeline catches it, retries within
its budget, and either continues in degraded mode or aborts and saves state.
"""
from _common import run_scenario

from src.failure_inject import scenarios

if __name__ == "__main__":
    run_scenario(
        title="Scenario 4 — MCP tool call fails (5xx)",
        scenario_slug="scenario-4-tool-failure",
        injector=scenarios.scenario_4_tool_failure(),
    )
