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
from src.guardrails import GuardrailBlocked, check_prompt_injection
from src.state import PipelineState, StateStore, events, resume_or_start

from .client import GatewayClient
from .failover_client import current_step_var
from .steps import PIPELINE_STEPS, Step
from .watchdog import ZombieStepDetected, call_with_watchdog


class PipelineError(RuntimeError):
    """The pipeline could not complete a step within its retry budget."""


def run_pipeline(
    client: GatewayClient,
    store: StateStore,
    pipeline_id: str,
    topic: str,
    max_retries_per_step: int = 2,
    watchdog_timeout_sec: float = 30.0,
) -> PipelineState:
    state, _resumed = resume_or_start(store, pipeline_id, topic)
    state.outputs.setdefault("topic", topic)

    while state.current_step < len(PIPELINE_STEPS):
        step = PIPELINE_STEPS[state.current_step]
        if not _run_one_step(
            client,
            store,
            state,
            step,
            pipeline_id,
            max_retries_per_step,
            watchdog_timeout_sec,
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
    watchdog_timeout_sec: float,
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
        # Publish step name on the contextvar so FailoverClient's fallback
        # callback can name the originating step in the FallbackUsed event
        # (FailoverClient doesn't otherwise know which step it's serving).
        current_step_var.set(step.name)
        try:
            user_prompt = step.build_user_prompt(state.outputs)
            # Input guardrail — runs *before* sending to the gateway. Blocks
            # prompt-injection vectors so they never reach the model. See
            # src/guardrails/prompt_injection.py for the pattern catalog.
            # A GuardrailBlocked is terminal: retrying with the same input
            # would just block again, so we let it propagate past the
            # retry loop below via the special-case handler.
            check_prompt_injection(user_prompt)
            # Watchdog — bound the wall-clock cost of a single attempt. A
            # zombie step (alive but making no progress) trips the timer
            # and gets converted into ZombieStepDetected, which the retry
            # loop handles like any other failure. See watchdog.py for the
            # thread-leak caveat.
            raw = call_with_watchdog(
                lambda: client.complete(step.model_pref, step.system_prompt, user_prompt),
                timeout_sec=watchdog_timeout_sec,
                step_name=step.name,
            )
            parsed = step.parse_output(raw)
            # Semantic postcondition — catches well-formed but unusable output
            # (empty arrays, two-word "articles", invalid enum values). See
            # self_test.py for the per-step checks. A failure here drives the
            # same retry path as a network error.
            step.postcondition(parsed)
        except GuardrailBlocked as gb:
            # Terminal — emit guardrail event and abort the pipeline. State
            # is saved so an operator can inspect what was blocked.
            store.append_event(
                events.GuardrailTriggered(
                    pipeline_id=pipeline_id,
                    step_name=step.name,
                    guardrail_name=gb.guardrail_name,
                    action="blocked",
                    detail=f"pattern={gb.pattern_name} snippet={gb.snippet!r}",
                )
            )
            state.mark_step_failed(step.name, "GuardrailBlocked", str(gb), step.model_pref)
            store.save_checkpoint(state)
            raise PipelineError(
                f"step {step.name!r}: input blocked by guardrail "
                f"{gb.guardrail_name!r} (pattern={gb.pattern_name!r})"
            ) from gb
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
                # final attempt exhausted; surface to caller, state is preserved.
                # All retry-exhausted exceptions are wrapped in PipelineError so
                # callers (chaos runner, demos, tests) have one type to catch.
                # The original exception is available via __cause__ if needed.
                if isinstance(exc, InjectedFailure):
                    raise PipelineError(
                        f"step {step.name!r}: exhausted {attempt} attempts under "
                        f"scenario {exc.scenario_name!r}"
                    ) from exc
                raise PipelineError(
                    f"step {step.name!r}: exhausted {attempt} attempts "
                    f"({type(exc).__name__}: {exc})"
                ) from exc
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
