"""StateStore — durable filesystem backend for PipelineState and events.

Two on-disk artefacts per pipeline_id (under base_dir):

  <base_dir>/<pipeline_id>/
    state.json          — latest checkpoint (crash-only atomic write)
    event_log.jsonl     — append-only event log

Design choices (the "why"):

  1. Crash-only writes (state.json is never updated in place). We write
     state.json.tmp.<pid> first, fsync, then os.replace() it onto state.json.
     os.replace is atomic on Windows and POSIX, so any crash leaves either
     the old state or the new state — never a half-written file.

  2. Append-only event log. New events are written with O_APPEND-equivalent
     semantics (one open()-write()-close() per event). Concurrent appends
     from one process are line-atomic because we write a single buffer that
     ends in '\n' in one syscall. Multi-process appends would need fcntl on
     POSIX; we do not support that — one pipeline per process.

  3. Per-pipeline isolation. Each pipeline_id gets its own directory so the
     event log of demo run #4 doesn't pollute the trace of demo run #5.

  4. Resume contract. load_latest() returns the last successfully saved
     state, or None if no state has ever been written. A pipeline that
     never wrote any checkpoint resumes from the beginning. A pipeline that
     wrote checkpoint N resumes at step N+1 — step N's output is already
     in state.outputs.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

from .events import Event
from .pipeline import PipelineState


class StateStore:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _pipeline_dir(self, pipeline_id: str) -> Path:
        d = self.base_dir / pipeline_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _state_path(self, pipeline_id: str) -> Path:
        return self._pipeline_dir(pipeline_id) / "state.json"

    def _event_log_path(self, pipeline_id: str) -> Path:
        return self._pipeline_dir(pipeline_id) / "event_log.jsonl"

    def save_checkpoint(self, state: PipelineState) -> None:
        """Atomically replace state.json with the current PipelineState.

        Order: write .tmp.<pid> → fsync → os.replace. The fsync ensures the
        new contents are durable on disk before the rename makes them
        visible. os.replace is atomic, so any crash leaves the filesystem
        with either the old or the new state.
        """
        path = self._state_path(state.pipeline_id)
        tmp = path.with_suffix(f".tmp.{os.getpid()}")
        payload = json.dumps(state.to_dict(), indent=2, ensure_ascii=False)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def load_latest(self, pipeline_id: str) -> PipelineState | None:
        path = self._state_path(pipeline_id)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return PipelineState.from_dict(json.load(f))

    def append_event(self, event: Event) -> None:
        """Append a single event as one JSONL line.

        We assemble the entire line as one bytes buffer with a trailing
        newline so a single write() syscall lands it atomically. Smaller
        than the OS pipe buffer is enough — we're writing <1KB per event.
        """
        path = self._event_log_path(event.pipeline_id)
        line = json.dumps(asdict(event), ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

    def read_events(self, pipeline_id: str) -> Iterator[dict]:
        path = self._event_log_path(pipeline_id)
        if not path.exists():
            return
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def list_pipelines(self) -> list[str]:
        return sorted(p.name for p in self.base_dir.iterdir() if p.is_dir())

    def gc_temp_files(self) -> int:
        """Remove orphan *.tmp.<pid> files left by previous crashes. Returns count removed."""
        removed = 0
        for p in self.base_dir.rglob("state.json.tmp.*"):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
        return removed
