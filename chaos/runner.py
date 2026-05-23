"""Chaos experiment runner.

Reads a Chaos Toolkit-shape experiment JSON, executes each `method`
action (Python function import + call), aggregates returned metrics,
and validates them against the `steady_state_hypothesis` probes.

Format (subset of chaostoolkit.org's spec — we don't need controls,
rollbacks-as-functions, or distributed runtimes):

    {
      "version": "1.0.0",
      "title": "...",
      "description": "...",
      "tags": [...],
      "steady_state_hypothesis": {
        "title": "...",
        "probes": [
          {"name": "<metric_key>", "tolerance": {"min": 0.0, "max": 1.0}}
        ]
      },
      "method": [
        {
          "name": "...",
          "provider": {
            "type": "python",
            "module": "chaos.injectors",
            "func": "<func_name>",
            "arguments": {...}
          }
        }
      ]
    }
"""
from __future__ import annotations

import importlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProbeResult:
    name: str
    observed: Any
    tolerance: dict[str, float]
    passed: bool


@dataclass
class ExperimentResult:
    title: str
    started_at: float
    duration_sec: float
    metrics: dict[str, Any]
    probes: list[ProbeResult]
    verdict: str  # "PASS" or "FAIL"
    experiment_file: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "experiment_file": self.experiment_file,
            "started_at": self.started_at,
            "duration_sec": self.duration_sec,
            "verdict": self.verdict,
            "metrics": self.metrics,
            "probes": [
                {
                    "name": p.name,
                    "observed": p.observed,
                    "tolerance": p.tolerance,
                    "passed": p.passed,
                }
                for p in self.probes
            ],
        }


def _resolve(module_name: str, func_name: str) -> Any:
    mod = importlib.import_module(module_name)
    return getattr(mod, func_name)


def _check_probe(probe: dict[str, Any], metrics: dict[str, Any]) -> ProbeResult:
    name = probe["name"]
    observed = metrics.get(name)
    tol = probe["tolerance"]
    if observed is None:
        return ProbeResult(name=name, observed=None, tolerance=tol, passed=False)
    lo = tol.get("min", float("-inf"))
    hi = tol.get("max", float("inf"))
    passed = lo <= observed <= hi
    return ProbeResult(name=name, observed=observed, tolerance=tol, passed=passed)


def run_experiment(spec: dict[str, Any]) -> ExperimentResult:
    title = spec.get("title", "<untitled>")
    t0 = time.time()

    # Execute every method step; merge their returned metrics dicts
    metrics: dict[str, Any] = {}
    for step in spec.get("method", []):
        prov = step.get("provider", {})
        if prov.get("type") != "python":
            continue
        fn = _resolve(prov["module"], prov["func"])
        result = fn(**prov.get("arguments", {}))
        if isinstance(result, dict):
            metrics.update(result)

    # Validate hypothesis probes
    hyp = spec.get("steady_state_hypothesis", {})
    probes = [_check_probe(p, metrics) for p in hyp.get("probes", [])]
    verdict = "PASS" if all(p.passed for p in probes) else "FAIL"

    return ExperimentResult(
        title=title,
        started_at=t0,
        duration_sec=time.time() - t0,
        metrics=metrics,
        probes=probes,
        verdict=verdict,
    )


def run_experiment_file(path: Path) -> ExperimentResult:
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    result = run_experiment(spec)
    result.experiment_file = str(path)
    return result
