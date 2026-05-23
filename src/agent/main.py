"""CLI entry point for the resilient SEO pipeline.

Examples:
  # Mock (no real LLM calls — works offline / while AWS approval pending)
  python -m src.agent.main --topic "best running shoes 2026" --mock

  # Real (requires TFY_API_KEY in env; routes through TrueFoundry → Bedrock)
  python -m src.agent.main --topic "best running shoes 2026"

  # Resume an interrupted run
  python -m src.agent.main --topic "..." --pipeline-id run-abcd1234
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

from src.state import StateStore

from .client import MockClient, TrueFoundryClient
from .pipeline import run_pipeline
from .steps import PIPELINE_STEPS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="resilient-seo-agent")
    parser.add_argument("--topic", required=True, help="SEO topic to generate a post about")
    parser.add_argument("--pipeline-id", default=None, help="Resume an existing run by ID")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use the canned MockClient instead of real LLM calls (useful while AWS approval pending)",
    )
    parser.add_argument("--state-dir", default=".session_state")
    args = parser.parse_args(argv)

    pipeline_id = args.pipeline_id or f"run-{uuid.uuid4().hex[:8]}"

    if args.mock:
        client = MockClient()
    else:
        api_key = os.environ.get("TFY_API_KEY")
        host = os.environ.get("TFY_HOST", "https://toxicbwi.truefoundry.cloud").rstrip("/")
        if not api_key:
            print("error: TFY_API_KEY not set. Use --mock to run offline.", file=sys.stderr)
            return 2
        client = TrueFoundryClient(api_key=api_key, base_url=f"{host}/api/llm")

    store = StateStore(args.state_dir)
    try:
        state = run_pipeline(client, store, pipeline_id, args.topic)
    except Exception as exc:
        print(f"pipeline aborted: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"state preserved under: {args.state_dir}/{pipeline_id}/")
        print(f"resume with: --pipeline-id {pipeline_id}")
        return 1

    print(f"pipeline_id: {pipeline_id}")
    print(f"completed: {state.current_step}/{len(PIPELINE_STEPS)} steps")
    print(f"steps done: {state.completed_steps}")

    if state.current_step == len(PIPELINE_STEPS):
        meta = state.outputs["optimize"].get("meta_description", "")
        print(f"meta_description: {meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
