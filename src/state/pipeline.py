"""PipelineState — the durable snapshot a pipeline can be resumed from."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PipelineState:
    """All the state a pipeline needs to resume after a crash or interruption.

    Saved atomically after every successful step. The on-disk JSON is the
    source of truth — in-memory state is just a cache. Loading the latest
    checkpoint and continuing must be observationally indistinguishable
    from never having crashed.
    """

    pipeline_id: str
    topic: str
    started_at: float = field(default_factory=time.time)
    current_step: int = 0  # 0..N; N means all done
    completed_steps: list[str] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)  # step_name -> payload
    failed_attempts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_step_done(self, step_name: str, output: Any) -> None:
        self.completed_steps.append(step_name)
        self.outputs[step_name] = output
        self.current_step += 1

    def mark_step_failed(
        self, step_name: str, error_type: str, error_msg: str, model: str
    ) -> None:
        self.failed_attempts.append(
            {
                "step": step_name,
                "error_type": error_type,
                "error_msg": error_msg,
                "model": model,
                "ts": time.time(),
            }
        )

    def is_done(self, total_steps: int) -> bool:
        return self.current_step >= total_steps

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PipelineState:
        return cls(
            pipeline_id=d["pipeline_id"],
            topic=d["topic"],
            started_at=d.get("started_at", time.time()),
            current_step=d.get("current_step", 0),
            completed_steps=d.get("completed_steps", []),
            outputs=d.get("outputs", {}),
            failed_attempts=d.get("failed_attempts", []),
            metadata=d.get("metadata", {}),
        )
