"""Scenario 7 — model returns well-formed JSON, but the content is wrong.

This is the hackathon's "bad intermediate outputs" failure mode in its
most subtle form. The response parses fine (parse_output is happy), but
the KEYWORD step returns an empty array. A downstream OUTLINE step
would then have no keywords to organize and would silently produce a
useless article.

The semantic postcondition (self_test.check_keyword) catches it: a
keyword response must have at least five usable entries. The failure
drives the standard retry path, the retry returns a normal response,
and the pipeline completes.

Run:
    python demos/scenario_7_semantic_hallucination.py

Expected: scenario completes, event log shows step_failed for keyword
followed by step_succeeded.
"""
from pathlib import Path
import sys

# Allow `python demos/scenario_7_semantic_hallucination.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import Counter

from _common import fresh_store

from src.agent.client import MockClient
from src.agent.pipeline import PipelineError, run_pipeline

# Force UTF-8 stdout so unicode arrows don't crash on Windows cp1251.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


def main() -> None:
    title = "Scenario 7 — semantic hallucination (well-formed but empty output)"
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)

    # Calls 1-5 are voice/keyword/outline/draft/optimize in order. Call 2 is
    # the KEYWORD step's first attempt — we make it return [] (valid JSON,
    # zero entries). The postcondition catches it.
    client = MockClient(hallucinate_calls=[2])
    store = fresh_store("scenario-7-semantic-hallucination")

    try:
        state = run_pipeline(client, store, "scenario-7-semantic-hallucination", "best running shoes 2026")
        aborted = False
    except PipelineError as exc:
        aborted = True
        print(f"\n[pipeline aborted]  {exc}")
        state = store.load_latest("scenario-7-semantic-hallucination")

    evs = list(store.read_events("scenario-7-semantic-hallucination"))
    counts = Counter(e["type"] for e in evs)
    print(f"\nEvent log: {len(evs)} events")
    for t in sorted(counts):
        print(f"  {t:<24} {counts[t]}")

    # Show the self-test error specifically — it's the headline detail.
    self_test_failures = [
        e for e in evs
        if e["type"] == "step_failed" and e.get("error_type") == "SelfTestFailed"
    ]
    print(f"\nSelf-test failures caught: {len(self_test_failures)}")
    for f in self_test_failures:
        print(f"  step={f['step_name']!r:<12} reason={f['error_msg']}")

    if state is not None:
        print(f"\nState:")
        print(f"  pipeline_id:        {state.pipeline_id}")
        print(f"  current_step:       {state.current_step}")
        print(f"  completed_steps:    {state.completed_steps}")

    if aborted:
        print("\n[WARN] expected completion but pipeline aborted")


if __name__ == "__main__":
    main()
