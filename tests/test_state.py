"""Tests for the state preservation layer.

Covers the four properties the demo depends on:
  1. Save/load roundtrip preserves PipelineState exactly.
  2. Resume after partial completion picks up at the right step.
  3. Event log is append-only and readable in order.
  4. Atomic-write contract: a crash mid-save never corrupts state.json.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from src.state import PipelineState, StateStore, events, resume_or_start


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path)


def test_save_load_roundtrip(store: StateStore) -> None:
    state = PipelineState(pipeline_id="p1", topic="running shoes")
    state.mark_step_done("voice", {"tone": "casual"})
    state.mark_step_done("keyword", {"primary": "best running shoes 2026"})
    store.save_checkpoint(state)

    loaded = store.load_latest("p1")
    assert loaded is not None
    assert loaded.pipeline_id == "p1"
    assert loaded.topic == "running shoes"
    assert loaded.current_step == 2
    assert loaded.completed_steps == ["voice", "keyword"]
    assert loaded.outputs["voice"] == {"tone": "casual"}
    assert loaded.outputs["keyword"]["primary"] == "best running shoes 2026"


def test_load_nonexistent_returns_none(store: StateStore) -> None:
    assert store.load_latest("never-existed") is None


def test_resume_or_start_fresh(store: StateStore) -> None:
    state, resumed = resume_or_start(store, "fresh", "topic-x")
    assert not resumed
    assert state.current_step == 0
    assert state.topic == "topic-x"

    evs = list(store.read_events("fresh"))
    assert len(evs) == 1
    assert evs[0]["type"] == "pipeline_started"


def test_resume_or_start_existing(store: StateStore) -> None:
    seed = PipelineState(pipeline_id="p2", topic="t")
    seed.mark_step_done("voice", {"v": 1})
    seed.mark_step_done("keyword", {"k": 2})
    store.save_checkpoint(seed)

    state, resumed = resume_or_start(store, "p2", "t")
    assert resumed
    assert state.current_step == 2
    assert state.outputs["voice"] == {"v": 1}

    evs = list(store.read_events("p2"))
    assert any(e["type"] == "pipeline_resumed" and e["from_step"] == 2 for e in evs)


def test_event_log_append_only_order(store: StateStore) -> None:
    pid = "p3"
    store.append_event(events.PipelineStarted(pipeline_id=pid, topic="t"))
    store.append_event(events.StepStarted(pipeline_id=pid, step_name="voice", step_index=0))
    store.append_event(
        events.StepSucceeded(
            pipeline_id=pid, step_name="voice", step_index=0, latency_ms=120, model_used="m1"
        )
    )

    evs = list(store.read_events(pid))
    assert [e["type"] for e in evs] == ["pipeline_started", "step_started", "step_succeeded"]
    # event log retains timestamps in nondecreasing order
    assert all(evs[i]["ts"] <= evs[i + 1]["ts"] for i in range(len(evs) - 1))


def test_atomic_save_no_corruption_on_partial_tmp(store: StateStore) -> None:
    """If a previous run crashed mid-write, leftover *.tmp.<pid> should not be
    visible as the current state. state.json must still parse cleanly."""
    state = PipelineState(pipeline_id="p4", topic="t")
    state.mark_step_done("voice", {"v": 1})
    store.save_checkpoint(state)

    # Simulate a crashed write by dropping a garbage .tmp file next to state.json.
    state_path = store.base_dir / "p4" / "state.json"
    garbage = state_path.with_suffix(".json.tmp.99999")
    garbage.write_text("not json {{{ corrupted", encoding="utf-8")

    # Loading should still succeed — we read state.json, not the tmp.
    loaded = store.load_latest("p4")
    assert loaded is not None
    assert loaded.outputs["voice"] == {"v": 1}

    # gc_temp_files cleans up the orphan.
    removed = store.gc_temp_files()
    assert removed == 1
    assert not garbage.exists()


def test_multiple_pipelines_isolated(store: StateStore) -> None:
    a = PipelineState(pipeline_id="A", topic="a-topic")
    b = PipelineState(pipeline_id="B", topic="b-topic")
    a.mark_step_done("voice", {"src": "A"})
    b.mark_step_done("voice", {"src": "B"})
    store.save_checkpoint(a)
    store.save_checkpoint(b)
    store.append_event(events.PipelineStarted(pipeline_id="A", topic="a-topic"))
    store.append_event(events.PipelineStarted(pipeline_id="B", topic="b-topic"))

    loaded_a = store.load_latest("A")
    loaded_b = store.load_latest("B")
    assert loaded_a is not None and loaded_a.outputs["voice"] == {"src": "A"}
    assert loaded_b is not None and loaded_b.outputs["voice"] == {"src": "B"}

    evs_a = list(store.read_events("A"))
    evs_b = list(store.read_events("B"))
    assert len(evs_a) == 1 and evs_a[0]["topic"] == "a-topic"
    assert len(evs_b) == 1 and evs_b[0]["topic"] == "b-topic"
