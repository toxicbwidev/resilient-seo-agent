"""Pipeline orchestrator.

Runs the steps from src.agent.steps in order, checkpointing after each
successful step and emitting events to the StateStore's event log. On a
failure it tries up to max_retries_per_step more times before raising.

Resume semantics: if a checkpoint already exists for `pipeline_id`,
execution skips the steps already in `state.completed_steps` and picks
up at the next one. The output of every prior step is already on disk
in state.outputs — there is no replay of earlier work.

The orchestrator is intentionally minimal. Recovery (priority-chain
fallback, circuit breaker, semantic cache) lives in the TrueFoundry
Gateway. This loop owns only the agent-level concerns: state, retries
within a step, and emitting telemetry events that map directly to the
failure-modes table in docs/failure-modes.md.
"""
from __future__ import annotations

import time
from typing import Any

from src.failure_inject import InjectedFailure
from src.state import PipelineState, StateStore, events, resume_or_start

from .client import GatewayClient
from .steps import PIPELINE_STEPS, Step


class PipelineError(RuntimeError):
    """The pipeline could not complete a step within its retry budget."""


def run_pipeline(
    client: GatewayClient,
    store: StateStore,
    pipeline_id: str,
    topic: str,
    max_retries_per_step: int = 2,
) -> PipelineState:
    state, _resumed = resume_or_start(store, pipeline_id, topic)
    state.outputs.setdefault("topic", topic)

    while state.current_step < len(PIPELINE_STEPS):
        step = PIPELINE_STEPS[state.current_step]
        if not _run_one_step(
            client, store, state, step, pipeline_id, max_retries_per_step
        ):
            return state  # exhausted retries; state is on disk

    store.append_event(
        events.PipelineCompleted(
            pipeline_id=pipeline_id,
            duration_sec=time.time() - state.started_at,
        )
    )
    return state


def _run_one_step(
    client: GatewayClient,
    store: StateStore,
    state: PipelineState,
    step: Step,
    pipeline_id: str,
    max_retries: int,
) -> bool:
    for attempt in range(1, max_retries + 2):
        store.append_event(
            events.StepStarted(
                pipeline_id=pipeline_id,
                step_name=step.name,
                step_index=state.current_step,
                attempt=attempt,
            )
        )
        t0 = time.time()
        try:
            user_prompt = step.build_user_prompt(state.outputs)
            raw = client.complete(step.model_pref, step.system_prompt, user_prompt)
            parsed = step.parse_output(raw)
        except Exception as exc:
            _emit_failure(store, pipeline_id, state, step, exc)
            if isinstance(exc, InjectedFailure):
                # injected failures are observable as "fallback used" in the
                # Gateway in production; here we only need to drive the
                # retry path so the pipeline observably recovers
                store.append_event(
                    events.FallbackUsed(
                        pipeline_id=pipeline_id,
                        step_name=step.name,
                        primary_model=step.model_pref,
                        fallback_model=step.model_pref,
                        reason=getattr(exc, "scenario_name", "injected"),
                    )
                )
            if attempt > max_retries:
                # final attempt exhausted; surface to caller, state is preserved
                if isinstance(exc, InjectedFailure):
                    raise PipelineError(
                        f"step {step.name!r}: exhausted {attempt} attempts under "
                        f"scenario {exc.scenario_name!r}"
                    ) from exc
                raise
            continue

        latency_ms = int((time.time() - t0) * 1000)
        store.append_event(
            events.StepSucceeded(
                pipeline_id=pipeline_id,
                step_name=step.name,
                step_index=state.current_step,
                latency_ms=latency_ms,
                model_used=step.model_pref,
            )
        )
        state.mark_step_done(step.name, parsed)
        store.save_checkpoint(state)
        store.append_event(
            events.CheckpointWritten(
                pipeline_id=pipeline_id,
                step_index=state.current_step,
                path=str(store._state_path(pipeline_id)),  # type: ignore[attr-defined]
            )
        )
        return True

    return False  # unreachable; loop above either returns True or raises


def _emit_failure(
    store: StateStore,
    pipeline_id: str,
    state: PipelineState,
    step: Step,
    exc: BaseException,
) -> None:
    store.append_event(
        events.StepFailed(
            pipeline_id=pipeline_id,
            step_name=step.name,
            step_index=state.current_step,
            error_type=type(exc).__name__,
            error_msg=str(exc),
            model_attempted=step.model_pref,
        )
    )
    state.mark_step_failed(step.name, type(exc).__name__, str(exc), step.model_pref)
