"""State preservation layer for the resilient pipeline.

Public surface:

  from src.state import PipelineState, StateStore, resume_or_start, events

  store = StateStore(".session_state")
  state = resume_or_start(store, pipeline_id="demo-1", topic="best running shoes")
  # ... run a step ...
  state.mark_step_done("voice_profile", {"tone": "casual"})
  store.save_checkpoint(state)
  store.append_event(events.StepSucceeded(
      pipeline_id=state.pipeline_id, step_name="voice_profile",
      step_index=1, latency_ms=820, model_used="claude-sonnet-4-6",
  ))
"""
from . import events
from .pipeline import PipelineState
from .store import StateStore


def resume_or_start(
    store: StateStore, pipeline_id: str, topic: str
) -> tuple[PipelineState, bool]:
    """Load existing state if any, else create fresh. Returns (state, resumed)."""
    existing = store.load_latest(pipeline_id)
    if existing is not None:
        store.append_event(
            events.PipelineResumed(
                pipeline_id=pipeline_id,
                from_step=existing.current_step,
                steps_already_done=list(existing.completed_steps),
            )
        )
        return existing, True

    state = PipelineState(pipeline_id=pipeline_id, topic=topic)
    store.save_checkpoint(state)
    store.append_event(events.PipelineStarted(pipeline_id=pipeline_id, topic=topic))
    return state, False


__all__ = ["PipelineState", "StateStore", "resume_or_start", "events"]
