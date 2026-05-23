"""Chaos engineering harness.

Hackathon brief: "stress-test it against failures like rate limits,
model or provider outages, slow responses, tool failures, bad
intermediate outputs, cascading errors across multiple steps."

This package implements that as actual chaos engineering experiments
in the Chaos Toolkit shape (https://chaostoolkit.org) — not a
hand-rolled stress loop. Each experiment under chaos/experiments/ has
a steady-state hypothesis, a method that injects faults, and a
measured result that either confirms or falsifies the hypothesis.

Run a single experiment:
    python -m chaos run chaos/experiments/01-rate-limit-tolerance.json

Run all experiments:
    python -m chaos run-all

Results land under chaos/results/ (gitignored except SUMMARY.md).
"""
from .runner import ExperimentResult, run_experiment_file

__all__ = ["ExperimentResult", "run_experiment_file"]
