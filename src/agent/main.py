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
import pathlib
import sys
import uuid

from src.state import StateStore, events

from .client import MockClient, TrueFoundryClient
from .failover_client import FailoverClient, current_step_var
from .pipeline import run_pipeline
from .steps import PIPELINE_STEPS


# Default model failover chain. Ordered by preference:
#   1) AWS Bedrock primary (sponsor stack — currently in real outage from KZ
#      due to account-level country block; failover is observable in
#      event_log.jsonl as FallbackUsed events, which IS the demo).
#   2) AWS Bedrock secondary (different model family — exercises chain depth
#      under the same outage).
#   3) Google Gemini via TF Gateway (requires Google Gemini integration in
#      TF Console; absent at first run will simply fail over to next).
#   4) Mistral La Plateforme via TF Gateway (verified working from KZ).
#   5) Mistral small as last resort (different model, less likely to share
#      rate-limit bucket with mistral-large).
#
# Override at runtime by setting FAILOVER_CHAIN to a comma-separated list.
DEFAULT_MODEL_CHAIN = [
    "aws-bedrock/us.anthropic.claude-sonnet-4-6",
    "aws-bedrock/us.meta.llama4-maverick-17b-instruct-v1-0",
    "google-gemini/gemini-2.5-flash-lite",
    "mistral-ai/mistral-large-latest",
    "mistral-ai/mistral-small-latest",
]


def _load_dotenv(path: str = ".env") -> None:
    """Tiny .env loader — KEY=VALUE per line, no quoting parsing.
    Project doesn't depend on python-dotenv; this is enough for our needs.
    Existing os.environ values are not overwritten.
    """
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


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

    store = StateStore(args.state_dir)

    if args.mock:
        client = MockClient()
    else:
        _load_dotenv()
        api_key = os.environ.get("TFY_API_KEY")
        host = os.environ.get("TFY_HOST", "https://toxicbwi.truefoundry.cloud").rstrip("/")
        if not api_key:
            print("error: TFY_API_KEY not set. Use --mock to run offline.", file=sys.stderr)
            return 2
        # TF AI Gateway OpenAI-compatible endpoint. Base URL must point at the
        # /v1 root because the openai SDK appends /chat/completions, /models, etc.
        raw_client = TrueFoundryClient(
            api_key=api_key,
            base_url=f"{host}/api/llm/api/inference/openai/v1",
        )

        # Resolve failover chain: env override → default constant.
        chain_env = os.environ.get("FAILOVER_CHAIN", "").strip()
        chain = (
            [m.strip() for m in chain_env.split(",") if m.strip()]
            if chain_env
            else list(DEFAULT_MODEL_CHAIN)
        )

        # Telemetry callback — emits a FallbackUsed event into the same
        # event_log.jsonl the rest of the pipeline writes to. Pipeline sets
        # current_step_var before each .complete() call so we can attribute
        # the fallback to the originating step.
        def _emit_fallback(from_model: str, to_model: str, exc: BaseException) -> None:
            step_name = current_step_var.get() or "?"
            reason = f"{type(exc).__name__}: {str(exc)[:160]}"
            store.append_event(
                events.FallbackUsed(
                    pipeline_id=pipeline_id,
                    step_name=step_name,
                    primary_model=from_model,
                    fallback_model=to_model,
                    reason=reason,
                )
            )
            print(
                f"[failover] step={step_name} {from_model} -> {to_model} ({type(exc).__name__})",
                file=sys.stderr,
            )

        client = FailoverClient(
            inner=raw_client,
            model_chain=chain,
            on_fallback=_emit_fallback,
        )
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
