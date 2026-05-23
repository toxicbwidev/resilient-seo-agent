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
from typing import Any, Protocol


class GatewayClient(Protocol):
    def complete(self, model_pref: str, system: str, user: str) -> str: ...


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

    def complete(self, model_pref: str, system: str, user: str) -> str:
        # `model_pref` is a routing-class alias the Gateway resolves to the
        # actual model in the priority chain (Claude → Mistral → Llama → Cohere).
        resp = self._client.chat.completions.create(
            model=f"resilient/{model_pref}",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""


class MockClient:
    """Canned-response client. Outputs match what parse_output() in steps.py expects."""

    def __init__(self) -> None:
        self.call_log: list[dict[str, Any]] = []

    def complete(self, model_pref: str, system: str, user: str) -> str:
        self.call_log.append({"model_pref": model_pref, "user_prefix": user[:120]})
        u = user.lower()

        # Order matters — check the most specific markers first.
        if "optimize" in u or "seo-revised" in u or "internal_links" in u:
            return json.dumps(
                {
                    "article": "# Best Running Shoes of 2026\n\nA tested-and-reviewed buyer's guide.\n\n## Methodology — Best Running Shoes of 2026\nWe ran the lineup over 200 km each.\n\n## Top Picks — Running Shoe Reviews\nThe podium...\n",
                    "meta_description": "Our 2026 picks for the best running shoes — methodology, top picks, sizing guide.",
                    "internal_links": ["Marathon training plan", "Pronation guide"],
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
            return (
                "# Best Running Shoes of 2026\n\n"
                "*Picking the right pair starts with knowing your gait.*\n\n"
                "## Methodology\n\nWe tested each model over 200 km of mixed terrain.\n\n"
                "## Top Picks\n\nThe three that earned a spot...\n\n"
                "## Sizing Guide\n\nFit before colour, always.\n"
            )
        if "keyword" in u and "json array" in u:
            return json.dumps(
                [
                    {"keyword": "best running shoes 2026", "intent": "commercial", "estimated_volume": "high"},
                    {"keyword": "running shoe reviews", "intent": "informational", "estimated_volume": "high"},
                    {"keyword": "running shoe fit", "intent": "informational", "estimated_volume": "medium"},
                ]
            )
        if "brand voice" in u or "voice" in u and "tone" in u:
            return json.dumps(
                {
                    "tone": "casual_authoritative",
                    "vocabulary_level": "intermediate",
                    "sentence_length": "medium",
                    "avoid_words": ["synergy", "leverage", "disrupt"],
                }
            )

        # Default — return an empty JSON object so parse_output won't crash
        # on unknown step content; caller should fail validation upstream.
        return "{}"


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
