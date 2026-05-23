"""CLI: python -m chaos run <experiment.json>
        python -m chaos run-all
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from .runner import ExperimentResult, run_experiment_file

EXPERIMENTS_DIR = Path("chaos/experiments")
RESULTS_DIR = Path("chaos/results")


def _print_result(result: ExperimentResult) -> None:
    bar = "=" * 72
    print()
    print(bar)
    sigil = "[PASS]" if result.passed else "[FAIL]"
    print(f"  {sigil}  {result.title}    ({result.duration_sec:.1f}s)")
    print(bar)
    for p in result.probes:
        sigil = "OK" if p.passed else "MISS"
        observed_s = (
            f"{p.observed:.3f}" if isinstance(p.observed, float) else str(p.observed)
        )
        tol = p.tolerance
        bound_s = f"[{tol.get('min', '-inf')}, {tol.get('max', 'inf')}]"
        print(f"  {sigil:<4} {p.name:<26} observed={observed_s:<8} tol={bound_s}")
    print(f"\n  Metrics:")
    for k, v in result.metrics.items():
        if k in {"outcomes_sample", "breakdown"}:
            continue
        v_s = f"{v:.3f}" if isinstance(v, float) else str(v)
        print(f"    {k:<28} {v_s}")
    bd = result.metrics.get("breakdown", {})
    if bd:
        print(f"  Failure breakdown:")
        for ftype in sorted(bd):
            print(f"    {ftype:<28} {bd[ftype]}")


def _save_result(result: ExperimentResult) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_title = result.title.replace(" ", "-").replace("/", "_")
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = RESULTS_DIR / f"{safe_title}-{stamp}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return path


def cmd_run(experiment_file: str) -> int:
    result = run_experiment_file(Path(experiment_file))
    _print_result(result)
    saved = _save_result(result)
    print(f"\n  Result JSON: {saved}")
    return 0 if result.passed else 1


def cmd_run_all() -> int:
    files = sorted(EXPERIMENTS_DIR.glob("*.json"))
    if not files:
        print(f"No experiments found in {EXPERIMENTS_DIR}")
        return 1
    results: list[ExperimentResult] = []
    for f in files:
        result = run_experiment_file(f)
        results.append(result)
        _print_result(result)
        _save_result(result)

    print()
    print("=" * 72)
    print(f"  SUMMARY: {sum(r.passed for r in results)}/{len(results)} experiments passed")
    print("=" * 72)
    for r in results:
        sigil = "[PASS]" if r.passed else "[FAIL]"
        print(f"  {sigil}  {r.title}")
    return 0 if all(r.passed for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chaos")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="run a single experiment file")
    p_run.add_argument("file", help="path to experiment JSON")
    sub.add_parser("run-all", help="run every experiment under chaos/experiments/")
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args.file)
    if args.cmd == "run-all":
        return cmd_run_all()
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
