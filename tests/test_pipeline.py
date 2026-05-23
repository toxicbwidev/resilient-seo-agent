"""End-to-end tests for the pipeline orchestrator.

These tests use the MockClient (canned outputs) plus an in-memory
StateStore (tmp_path) so they run in milliseconds and exercise the
state + injection + orchestrator integration without touching a real
LLM. The whole point of the failure injection harness is that this is
how we get reproducible coverage of recovery paths."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.client import MockClient, wrap_with_injection
from src.agent.pipeline import PipelineError, run_pipeline
from src.agent.steps import PIPELINE_STEPS
from src.failure_inject import scenarios
from src.state import StateStore


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path)


def test_happy_path_runs_all_steps(store: StateStore) -> None:
    client = MockClient()
    state = run_pipeline(client, store, "happy-1", "best running shoes 2026")

    assert state.current_step == len(PIPELINE_STEPS)
    assert state.completed_steps == ["voice", "keyword", "outline", "draft", "optimize"]
    assert "meta_description" in state.outputs["optimize"]

    # event log has the right shape
    types = [e["type"] for e in store.read_events("happy-1")]
    assert types[0] == "pipeline_started"
    assert types[-1] == "pipeline_completed"
    assert types.count("step_succeeded") == 5
    assert types.count("checkpoint_written") == 5


def test_resume_skips_completed_steps(store: StateStore, tmp_path: Path) -> None:
    """Run the pipeline once, then resume with the same pipeline_id and
    confirm the second run doesn't re-execute any step."""
    client = MockClient()
    run_pipeline(client, store, "resume-1", "topic")

    calls_after_first_run = len(client.call_log)
    assert calls_after_first_run == 5  # one call per step

    # Run again with the same pipeline_id
    run_pipeline(client, store, "resume-1", "topic")
    # No additional model calls — every step was already done.
    assert len(client.call_log) == calls_after_first_run


def test_injected_rate_limit_recovers_within_retry_budget(store: StateStore) -> None:
    """Call 1 hits rate limit; call 2 succeeds. Pipeline should finish."""
    client = MockClient()
    injector = scenarios.scenario_1_rate_limit()  # plan {1: rate_limit, 2: rate_limit}
    # With 2 retries (default), first step takes calls 1, 2, 3 — call 3 succeeds.
    # Remaining 4 steps each take one call.
    wrapped = wrap_with_injection(client, injector)

    state = run_pipeline(wrapped, store, "inject-1", "topic")

    assert state.current_step == len(PIPELINE_STEPS)
    # injector fired exactly twice — calls 1 and 2.
    assert len(injector.injections_fired) == 2

    types = [e["type"] for e in store.read_events("inject-1")]
    assert types.count("step_failed") == 2
    assert types.count("fallback_used") == 2
    assert types.count("step_succeeded") == 5  # all 5 steps eventually win


def test_pipeline_aborts_when_retries_exhausted(store: StateStore) -> None:
    """Provider outage scenario fails calls 1, 2, 3. Step 1 with 2 retries
    gets calls 1, 2, 3 — all fail — pipeline aborts. State must be preserved
    so a later run can resume."""
    client = MockClient()
    injector = scenarios.scenario_2_provider_outage()
    wrapped = wrap_with_injection(client, injector)

    with pytest.raises(PipelineError):
        run_pipeline(wrapped, store, "abort-1", "topic")

    # State on disk: voice step never completed.
    loaded = store.load_latest("abort-1")
    assert loaded is not None
    assert loaded.current_step == 0
    assert loaded.completed_steps == []

    # Event log shows the 3 failures.
    types = [e["type"] for e in store.read_events("abort-1")]
    assert types.count("step_failed") == 3


def test_resume_after_partial_completion(store: StateStore) -> None:
    """Simulate: voice + keyword done, then crash. Resume picks up at outline."""
    client = MockClient()
    # Step 1: run normally — get voice + keyword done, then break.
    # We do this by running through one step at a time using state directly.
    from src.state import PipelineState

    state = PipelineState(pipeline_id="partial-1", topic="topic")
    state.outputs["topic"] = "topic"
    # Manually mark voice and keyword as done with canned outputs
    state.mark_step_done("voice", {"tone": "casual_authoritative"})
    state.mark_step_done(
        "keyword",
        [{"keyword": "best running shoes 2026", "intent": "commercial"}],
    )
    store.save_checkpoint(state)

    # Resume — should run outline, draft, optimize only.
    new_state = run_pipeline(client, store, "partial-1", "topic")

    assert new_state.completed_steps == ["voice", "keyword", "outline", "draft", "optimize"]
    # Only 3 model calls happened on this run.
    assert len(client.call_log) == 3
