"""Tests for the watchdog (zombie-step detection)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.client import MockClient
from src.agent.pipeline import PipelineError, run_pipeline
from src.agent.watchdog import ZombieStepDetected, call_with_watchdog
from src.state import StateStore


# --- call_with_watchdog primitive -----------------------------------------

def test_returns_value_on_fast_path() -> None:
    assert call_with_watchdog(lambda: 42, timeout_sec=1.0) == 42


def test_re_raises_function_exception() -> None:
    def boom() -> None:
        raise ValueError("planned")
    with pytest.raises(ValueError, match="planned"):
        call_with_watchdog(boom, timeout_sec=1.0)


def test_timeout_raises_zombie_detected() -> None:
    def hang() -> None:
        time.sleep(0.5)
    t0 = time.time()
    with pytest.raises(ZombieStepDetected) as ex:
        call_with_watchdog(hang, timeout_sec=0.1, step_name="my_step")
    elapsed = time.time() - t0
    assert ex.value.step_name == "my_step"
    assert ex.value.timeout_sec == 0.1
    # The watchdog should fire before the sleep finishes
    assert elapsed < 0.4


def test_zero_timeout_skips_watchdog() -> None:
    """A timeout of 0 means 'no watchdog' — run fn synchronously."""
    assert call_with_watchdog(lambda: "ok", timeout_sec=0) == "ok"


# --- end-to-end: pipeline recovers from a zombie step ----------------------

def test_pipeline_recovers_from_zombie_step(tmp_path: Path) -> None:
    """First model call hangs > timeout; second call returns normally."""
    client = MockClient(hang_calls=[1], hang_seconds=0.5)
    store = StateStore(tmp_path / "state")

    state = run_pipeline(
        client,
        store,
        "test-zombie",
        "best running shoes 2026",
        watchdog_timeout_sec=0.1,
    )

    assert state.is_done(5)
    evs = list(store.read_events("test-zombie"))
    zombie_failures = [e for e in evs if e.get("error_type") == "ZombieStepDetected"]
    assert len(zombie_failures) == 1
    assert zombie_failures[0]["step_name"] == "voice"


def test_pipeline_aborts_when_every_call_hangs(tmp_path: Path) -> None:
    """If every retry hangs, pipeline exhausts retries and aborts cleanly."""
    # max_retries=2 → 3 attempts on voice (calls 1, 2, 3). Hang all three.
    client = MockClient(hang_calls=[1, 2, 3], hang_seconds=0.5)
    store = StateStore(tmp_path / "state")

    with pytest.raises(Exception):
        run_pipeline(
            client,
            store,
            "test-zombie-exhaust",
            "test topic",
            watchdog_timeout_sec=0.1,
        )

    state = store.load_latest("test-zombie-exhaust")
    assert state is not None
    assert state.completed_steps == []
    assert state.current_step == 0
