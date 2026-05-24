"""LLM gateway clients.

Two concrete clients:

  - TrueFoundryClient — real client. Uses the openai SDK pointed at the
    TrueFoundry AI Gateway's OpenAI-compatible endpoint. The Gateway in
    turn forwards to AWS Bedrock with our configured priority chain and
    guardrails. Requires TFY_API_KEY and TFY_HOST in env.

  - MockClient — returns canned outputs based on substrings in the user
    prompt. Used for tests, for the failure-injection demo (where we
    inject failures via wrap_with_injection regardless of the underlying
    client), and as the offline path while AWS Bedrock InvokeModel is
    still gated by AWS support.

Both implement the GatewayClient Protocol: a single .complete(model_pref,
system, user) -> str method.
"""
from __future__ import annotations

import json
import os
from typing import Any, Protocol


class GatewayClient(Protocol):
    def complete(
        self,
        model_pref: str,
        system: str,
        user: str,
        model_override: str | None = None,
    ) -> str: ...


class TrueFoundryClient:
    """Real client — uses openai SDK against TrueFoundry's gateway endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_sec: float = 60.0,
    ) -> None:
        # Lazy import: openai isn't needed for the mock path.
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_sec)

    def complete(
        self,
        model_pref: str,
        system: str,
        user: str,
        model_override: str | None = None,
    ) -> str:
        # Resolve model name in priority order:
        #   1) Per-call model_override (FailoverClient passes this — picks the
        #      current model from its chain on each retry attempt).
        #   2) TFY_MODEL_OVERRIDE env var (single-model override for ops).
        #   3) "resilient/<model_pref>" → resolves through a TF Gateway routing
        #      rule named "resilient" (Claude → Mistral → ... chain). Requires
        #      the rule to exist; deliberately NOT relied on for resilience
        #      since we want failover in the agent code, not the gateway.
        model = (
            model_override
            or os.environ.get("TFY_MODEL_OVERRIDE")
            or f"resilient/{model_pref}"
        )
        resp = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""


class MockClient:
    """Canned-response client. Outputs match what parse_output() in steps.py
    expects AND pass the per-step semantic postconditions in self_test.py.

    Modes (1-indexed call numbers):
      - normal (default): healthy responses for all five steps
      - hallucinate_calls: calls on which to return a well-formed but
        semantically insufficient response (empty arrays, too-short
        drafts). Other calls fall back to normal.
      - hang_calls: calls on which to sleep `hang_seconds` before
        responding. Simulates a model that's gone zombie. Pair with the
        watchdog wrapper to drive the recovery path in tests.
    """

    def __init__(
        self,
        hallucinate_calls: list[int] | None = None,
        hang_calls: list[int] | None = None,
        hang_seconds: float = 0.0,
    ) -> None:
        self.call_log: list[dict[str, Any]] = []
        self._hallucinate_calls = set(hallucinate_calls or [])
        self._hang_calls = set(hang_calls or [])
        self._hang_seconds = hang_seconds

    def complete(self, model_pref: str, system: str, user: str) -> str:
        self.call_log.append({"model_pref": model_pref, "user_prefix": user[:120]})
        call_idx = len(self.call_log)  # 1-indexed
        if call_idx in self._hang_calls and self._hang_seconds > 0:
            import time as _time
            _time.sleep(self._hang_seconds)
        if call_idx in self._hallucinate_calls:
            return self._hallucinated_response(user)
        return self._normal_response(user)

    def _normal_response(self, user: str) -> str:
        u = user.lower()
        # Order matters — check the most specific markers first.
        if "optimize" in u or "seo-revised" in u or "internal_links" in u:
            return json.dumps(
                {
                    "article": (
                        "# Best Running Shoes of 2026\n\n"
                        "A tested-and-reviewed buyer's guide based on 200 km per pair "
                        "across road, trail, and track surfaces.\n\n"
                        "## Methodology — Best Running Shoes of 2026\n"
                        "We ran each model 200 km on three surfaces, measured midsole "
                        "compression after 100 km, and logged subjective comfort on a "
                        "10-point scale.\n\n"
                        "## Top Picks — Running Shoe Reviews\n"
                        "Three shoes earned a podium spot: a daily trainer, a tempo "
                        "shoe, and a max-cushion long-run shoe.\n\n"
                        "## Sizing Guide — Running Shoe Fit\n"
                        "Size up half a size from your street shoes, account for toe "
                        "splay, leave a thumb's width at the toe box.\n"
                    ),
                    "meta_description": "Our 2026 picks for the best running shoes — methodology, top picks, sizing guide.",
                    "internal_links": ["Marathon training plan", "Pronation guide", "Heel-strike vs midfoot"],
                }
            )
        if "outline" in u and "json outline" in u:
            return json.dumps(
                {
                    "h1": "Best Running Shoes of 2026",
                    "sections": [
                        {"h2": "Methodology", "target_keyword": "running shoe reviews"},
                        {"h2": "Top Picks", "target_keyword": "best running shoes 2026"},
                        {"h2": "Sizing Guide", "target_keyword": "running shoe fit"},
                    ],
                    "intro_hook": "Picking the right pair starts with knowing your gait.",
                }
            )
        if "write the full article body" in u or "~800 words" in u:
            # Realistic-length article (>300 words) — passes check_draft.
            return _SAMPLE_DRAFT
        if "keyword" in u and "json array" in u:
            return json.dumps(
                [
                    {"keyword": "best running shoes 2026", "intent": "commercial", "estimated_volume": "high"},
                    {"keyword": "running shoe reviews", "intent": "informational", "estimated_volume": "high"},
                    {"keyword": "running shoe fit", "intent": "informational", "estimated_volume": "medium"},
                    {"keyword": "marathon training plan", "intent": "informational", "estimated_volume": "medium"},
                    {"keyword": "pronation guide", "intent": "informational", "estimated_volume": "low"},
                    {"keyword": "trail running shoes", "intent": "commercial", "estimated_volume": "medium"},
                ]
            )
        if "brand voice" in u or ("voice" in u and "tone" in u):
            return json.dumps(
                {
                    "tone": "casual_authoritative",
                    "vocabulary_level": "intermediate",
                    "sentence_length": "medium",
                    "avoid_words": ["synergy", "leverage", "disrupt"],
                }
            )
        return "{}"

    def _hallucinated_response(self, user: str) -> str:
        """Valid JSON / valid markdown, but semantically insufficient.

        Each branch returns content that parse_output() will accept but a
        sensible postcondition will reject. This is exactly the failure
        mode the hackathon brief calls "bad intermediate outputs".
        """
        u = user.lower()
        if "optimize" in u or "seo-revised" in u or "internal_links" in u:
            return json.dumps(
                {
                    "article": "too short.",
                    "meta_description": "tiny.",  # 5 chars — fails 50..160 bound
                    "internal_links": [],
                }
            )
        if "outline" in u and "json outline" in u:
            return json.dumps({"h1": "X", "sections": [], "intro_hook": ""})
        if "write the full article body" in u or "~800 words" in u:
            return "# Title\n\nOne line."  # ~3 words — fails >=300
        if "keyword" in u and "json array" in u:
            return json.dumps([])  # empty array — fails >=5
        if "brand voice" in u or ("voice" in u and "tone" in u):
            return json.dumps({"tone": "", "vocabulary_level": "guru", "sentence_length": "epic"})
        return "{}"


# Realistic-length sample article (~340 words). Passes check_draft.
_SAMPLE_DRAFT = (
    "# Best Running Shoes of 2026\n\n"
    "*Picking the right pair starts with knowing your gait.*\n\n"
    "## Methodology\n\n"
    "We tested each model over 200 km of mixed terrain — paved bike paths, "
    "wooded singletrack, and a 400-metre track for split work. Every shoe "
    "got the same protocol: a five-kilometre easy run on day one, a "
    "tempo workout in the second week, a long run in the third, and a "
    "session of strides on the track in the fourth. We measured midsole "
    "compression after every block with a digital caliper and logged "
    "subjective comfort on a ten-point scale at the end of each run. "
    "Outsole wear was photographed monthly under controlled lighting and "
    "compared against the manufacturer's published wear pattern.\n\n"
    "## Top Picks\n\n"
    "Three shoes earned a podium spot this year. The daily trainer is a "
    "moderate-stack neutral shoe that disappears underfoot at easy paces "
    "and still gives you a usable shape for the occasional surge. The "
    "tempo shoe is a lighter, firmer ride — best at five to ten kilometres "
    "per hour above your easy pace, less forgiving below that. The "
    "max-cushion long-run shoe is the surprise of the year: a "
    "twenty-eight-millimetre stack height with a rocker geometry that "
    "actually saves the legs at hour two and beyond, not just for the "
    "marathon crowd.\n\n"
    "## Sizing Guide\n\n"
    "Size up half a size from your street shoes for most road models — "
    "feet swell on long runs and you want a thumb's width at the toe box. "
    "Trail shoes can be even larger if you'll be doing technical descents "
    "where your toes hit the front of the shoe. Width matters as much as "
    "length: a too-narrow shoe causes black toenails before a too-long "
    "shoe causes blisters. Try them on at the end of the day when your "
    "feet are already a little swollen, and bring the socks you actually "
    "run in.\n"
)


def wrap_with_injection(client: GatewayClient, injector) -> GatewayClient:
    """Return a new client whose .complete is the original wrapped through
    the injector. Used by demo scripts to drive specific failure scenarios.
    """

    class _Wrapped:
        def __init__(self, real: GatewayClient, inj) -> None:
            self._real = real
            self._inj = inj
            self._wrapped = inj.wrap(real.complete)

        def complete(self, model_pref: str, system: str, user: str) -> str:
            return self._wrapped(model_pref, system, user)

    return _Wrapped(client, injector)
