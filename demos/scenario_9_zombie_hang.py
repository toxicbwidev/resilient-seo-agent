"""Scenario 9 — step goes zombie (alive but making no progress).

The model provider stops responding mid-stream — the socket is open,
the connection is alive, the agent is "running" — but no bytes are
flowing. A retry loop that only triggers on exceptions will never fire.
The pipeline appears to be working but produces nothing.

The watchdog (src/agent/watchdog.py) wraps each model call with a
timeout. When the timeout trips, ZombieStepDetected is raised and the
pipeline's standard retry path runs. In this demo:

  - Call 1 (VOICE attempt 1) hangs for 2 seconds; watchdog timeout is
    0.5 seconds, so it trips at 0.5s.
  - Call 2 (VOICE retry) does not hang; pipeline completes.

Run:
    python demos/scenario_9_zombie_hang.py

Expected: scenario completes, one ZombieStepDetected in the log, then
the pipeline recovers and finishes all five steps.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import Counter

from _common import fresh_store

from src.agent.client import MockClient
from src.agent.pipeline import PipelineError, run_pipeline

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


def main() -> None:
    title = "Scenario 9 — zombie step (hang detected by watchdog)"
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)

    # Call 1 (voice attempt 1) hangs 2 seconds; watchdog timeout 0.5 sec
    # fires first. Subsequent calls don't hang, so the retry succeeds.
    client = MockClient(hang_calls=[1], hang_seconds=2.0)
    store = fresh_store("scenario-9-zombie-hang")

    try:
        state = run_pipeline(
            client,
            store,
            "scenario-9-zombie-hang",
            "best running shoes 2026",
            watchdog_timeout_sec=0.5,
        )
        aborted = False
    except PipelineError as exc:
        aborted = True
        print(f"\n[pipeline aborted]  {exc}")
        state = store.load_latest("scenario-9-zombie-hang")

    evs = list(store.read_events("scenario-9-zombie-hang"))
    counts = Counter(e["type"] for e in evs)
    print(f"\nEvent log: {len(evs)} events")
    for t in sorted(counts):
        print(f"  {t:<24} {counts[t]}")

    zombie_failures = [
        e for e in evs
        if e["type"] == "step_failed" and e.get("error_type") == "ZombieStepDetected"
    ]
    print(f"\nZombie detections: {len(zombie_failures)}")
    for f in zombie_failures:
        print(f"  step={f['step_name']!r:<10} reason={f['error_msg']}")

    if state is not None:
        print(f"\nState:")
        print(f"  pipeline_id:        {state.pipeline_id}")
        print(f"  current_step:       {state.current_step}")
        print(f"  completed_steps:    {state.completed_steps}")

    if aborted:
        print("\n[WARN] expected pipeline to recover, but it aborted")


if __name__ == "__main__":
    main()
