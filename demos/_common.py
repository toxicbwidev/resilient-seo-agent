"""Shared helpers for the six demo scripts.

Each demo script picks one scenario from src.failure_inject.scenarios,
wraps the MockClient through it, runs the pipeline, then prints a human-
readable summary of the event log so a viewer can see what failed and
what recovered.
"""
from __future__ import annotations

import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Force UTF-8 stdout so unicode arrows / em-dashes don't crash on Windows cp1251.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # Python 3.7+
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# Allow running these scripts via `python demos/scenario_*.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.client import MockClient, wrap_with_injection  # noqa: E402
from src.agent.pipeline import PipelineError, run_pipeline  # noqa: E402
from src.failure_inject import FailureInjector  # noqa: E402
from src.state import StateStore  # noqa: E402


def fresh_store(scenario_slug: str) -> StateStore:
    """Drop any prior state for this scenario so reruns are reproducible."""
    base = Path(".session_state_demos") / scenario_slug
    if base.exists():
        shutil.rmtree(base)
    return StateStore(base)


def run_scenario(
    title: str,
    scenario_slug: str,
    injector: FailureInjector,
    expect_abort: bool = False,
) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)

    store = fresh_store(scenario_slug)
    client = wrap_with_injection(MockClient(), injector)

    try:
        state = run_pipeline(client, store, scenario_slug, "best running shoes 2026")
        aborted = False
    except PipelineError as exc:
        aborted = True
        print(f"\n[pipeline aborted]  {exc}")
        state = store.load_latest(scenario_slug)

    _print_log_summary(store, scenario_slug, injector)
    _print_state_summary(state)

    if expect_abort and not aborted:
        print("\n[WARN] expected pipeline to abort but it completed")
    if not expect_abort and aborted:
        print("\n[WARN] expected completion but pipeline aborted")


def _print_log_summary(store: StateStore, pipeline_id: str, injector) -> None:
    evs = list(store.read_events(pipeline_id))
    counts = Counter(e["type"] for e in evs)
    print(f"\nEvent log: {len(evs)} events")
    for t in sorted(counts):
        print(f"  {t:<24} {counts[t]}")
    print(f"\nInjections fired: {len(injector.injections_fired)}")
    for inj in injector.injections_fired:
        delay = f" delay={inj.get('delay_sec', 0):.3f}s" if inj.get("type") == "slow" else ""
        print(f"  call #{inj['call']:<2} type={inj['type']}{delay}")


def _print_state_summary(state: Any) -> None:
    if state is None:
        print("\nState: (none — pipeline never saved a checkpoint)")
        return
    print(f"\nState:")
    print(f"  pipeline_id:        {state.pipeline_id}")
    print(f"  current_step:       {state.current_step}")
    print(f"  completed_steps:    {state.completed_steps}")
    print(f"  failed_attempts:    {len(state.failed_attempts)}")
