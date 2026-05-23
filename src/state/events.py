"""Event types for the pipeline append-only event log.

Every interesting transition in pipeline execution is recorded as a typed
event in event_log.jsonl. The log is append-only (we never rewrite or
delete entries) so it's safe to tail in real time during a demo and to
replay for post-mortem analysis.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Event:
    """Base event. Subclasses set `type` and add their own payload fields."""

    type: str = ""
    pipeline_id: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineStarted(Event):
    type: str = "pipeline_started"
    topic: str = ""


@dataclass
class PipelineResumed(Event):
    type: str = "pipeline_resumed"
    from_step: int = 0
    steps_already_done: list[str] = field(default_factory=list)


@dataclass
class PipelineCompleted(Event):
    type: str = "pipeline_completed"
    duration_sec: float = 0.0


@dataclass
class StepStarted(Event):
    type: str = "step_started"
    step_name: str = ""
    step_index: int = 0
    attempt: int = 1


@dataclass
class StepSucceeded(Event):
    type: str = "step_succeeded"
    step_name: str = ""
    step_index: int = 0
    latency_ms: int = 0
    model_used: str = ""


@dataclass
class StepFailed(Event):
    type: str = "step_failed"
    step_name: str = ""
    step_index: int = 0
    error_type: str = ""
    error_msg: str = ""
    model_attempted: str = ""


@dataclass
class FallbackUsed(Event):
    type: str = "fallback_used"
    step_name: str = ""
    primary_model: str = ""
    fallback_model: str = ""
    reason: str = ""


@dataclass
class GuardrailTriggered(Event):
    type: str = "guardrail_triggered"
    step_name: str = ""
    guardrail_name: str = ""
    action: str = ""  # "blocked" | "redacted" | "audit"
    detail: str = ""


@dataclass
class CheckpointWritten(Event):
    type: str = "checkpoint_written"
    step_index: int = 0
    path: str = ""
