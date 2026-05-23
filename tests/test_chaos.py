"""Tests for the chaos experiment framework itself.

Validates: probe-checking logic, runner orchestration, injector
determinism, required metric keys. Does NOT run the full chaos
experiments — those land under chaos/results/ and have their own
PASS/FAIL semantics.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chaos.injectors import (
    mixed_chaos,
    rate_limit_chaos,
)
from chaos.random_client import FailureProfile, RandomFailureClient
from chaos.runner import _check_probe, run_experiment


# --- Probe-checking primitive ---------------------------------------------

def test_probe_pass_when_observed_in_tolerance() -> None:
    res = _check_probe(
        {"name": "completion_rate", "tolerance": {"min": 0.5, "max": 1.0}},
        {"completion_rate": 0.8},
    )
    assert res.passed
    assert res.observed == 0.8


def test_probe_fail_when_observed_below_min() -> None:
    res = _check_probe(
        {"name": "completion_rate", "tolerance": {"min": 0.9, "max": 1.0}},
        {"completion_rate": 0.5},
    )
    assert not res.passed


def test_probe_fail_when_observed_above_max() -> None:
    res = _check_probe(
        {"name": "crash_rate", "tolerance": {"min": 0.0, "max": 0.0}},
        {"crash_rate": 0.1},
    )
    assert not res.passed


def test_probe_fail_when_metric_missing() -> None:
    res = _check_probe(
        {"name": "completion_rate", "tolerance": {"min": 0.0, "max": 1.0}},
        {"other_metric": 0.5},
    )
    assert not res.passed
    assert res.observed is None


# --- Runner orchestrates correctly ----------------------------------------

def test_runner_verdict_pass_when_all_probes_pass() -> None:
    spec = {
        "title": "test",
        "steady_state_hypothesis": {
            "probes": [
                {"name": "x", "tolerance": {"min": 0.0, "max": 1.0}},
            ],
        },
        "method": [
            {
                "name": "fake",
                "provider": {
                    "type": "python",
                    "module": "tests.test_chaos",
                    "func": "_fake_injector",
                    "arguments": {"value": 0.5},
                },
            },
        ],
    }
    result = run_experiment(spec)
    assert result.verdict == "PASS"


def test_runner_verdict_fail_when_any_probe_fails() -> None:
    spec = {
        "title": "test",
        "steady_state_hypothesis": {
            "probes": [
                {"name": "x", "tolerance": {"min": 0.7, "max": 1.0}},
            ],
        },
        "method": [
            {
                "name": "fake",
                "provider": {
                    "type": "python",
                    "module": "tests.test_chaos",
                    "func": "_fake_injector",
                    "arguments": {"value": 0.5},
                },
            },
        ],
    }
    result = run_experiment(spec)
    assert result.verdict == "FAIL"


def _fake_injector(value: float) -> dict:
    """Test helper — returns {x: value} so we can drive runner deterministically."""
    return {"x": value}


# --- RandomFailureClient: determinism + behavior --------------------------

def test_zero_profile_passes_through(tmp_path: Path) -> None:
    """With zero failure probabilities, every call hits the real client."""
    from src.agent.client import MockClient
    rc = RandomFailureClient(MockClient(), FailureProfile(), seed=0)
    out = rc.complete("creative", "sys", "brand voice tone")
    assert out != ""
    assert rc.injection_log == []


def test_same_seed_produces_same_injections() -> None:
    """Determinism: identical seeds → identical injection sequences."""
    from src.agent.client import MockClient
    profile = FailureProfile(rate_limit=0.5, outage=0.3)
    rc1 = RandomFailureClient(MockClient(), profile, seed=12345)
    rc2 = RandomFailureClient(MockClient(), profile, seed=12345)
    for _ in range(20):
        # Both should raise/return identically — we don't care which, just same
        try:
            rc1.complete("x", "y", "brand voice tone")
        except Exception:
            pass
        try:
            rc2.complete("x", "y", "brand voice tone")
        except Exception:
            pass
    assert [r.failure_type for r in rc1.injection_log] == [
        r.failure_type for r in rc2.injection_log
    ]


# --- Injector returns all required metric keys ----------------------------

REQUIRED_METRIC_KEYS = {
    "n_pipelines",
    "completion_rate",
    "abort_rate",
    "crash_rate",
    "state_integrity_rate",
    "mean_retries",
    "failures_per_pipeline",
    "breakdown",
}


def test_rate_limit_chaos_returns_required_keys() -> None:
    m = rate_limit_chaos(n_pipelines=3, probability=0.1, seed=1, concurrency=1)
    missing = REQUIRED_METRIC_KEYS - set(m.keys())
    assert not missing, f"missing keys: {missing}"


def test_mixed_chaos_smoke() -> None:
    """End-to-end: run 3 pipelines under mixed chaos, no exceptions, valid metrics."""
    m = mixed_chaos(n_pipelines=3, seed=7, concurrency=1, watchdog_timeout_sec=1.0)
    assert m["n_pipelines"] == 3
    assert 0.0 <= m["completion_rate"] <= 1.0
    assert m["crash_rate"] == 0.0  # crashes are bugs, never expected
    assert m["state_integrity_rate"] == 1.0
