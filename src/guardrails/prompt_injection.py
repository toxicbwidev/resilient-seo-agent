"""Prompt-injection detection.

Catches the classic vectors documented in OWASP LLM01 and the
prompt-injection research literature (Greshake et al. 2023, Perez & Ribeiro
2022). Patterns are intentionally narrow — false positives on legitimate
SEO content (which is what this agent processes) are worse than the
occasional miss, because a triggered guardrail aborts the pipeline.

Application point: the agent calls check_prompt_injection on every
user_prompt before sending it to the gateway. This sits in front of the
TrueFoundry Gateway's own input guardrail (see
guardrails/04-input-prompt-injection-block.json) — same check, two
layers, the agent layer is what the demo harness can observe directly.

Returning is split into two functions on purpose:

  - detect_prompt_injection(text) -> list of matched pattern names. Used
    for audit-only enforcement and for testing.
  - check_prompt_injection(text) -> None. Raises GuardrailBlocked on
    the first match. Used in the pipeline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class GuardrailBlocked(RuntimeError):
    """A guardrail rejected the input. Terminal — do not retry with the same input."""

    def __init__(self, guardrail_name: str, pattern_name: str, snippet: str) -> None:
        super().__init__(
            f"guardrail {guardrail_name!r} blocked input "
            f"(pattern={pattern_name!r}): {snippet!r}"
        )
        self.guardrail_name = guardrail_name
        self.pattern_name = pattern_name
        self.snippet = snippet


@dataclass(frozen=True)
class _Pattern:
    name: str
    regex: re.Pattern[str]
    rationale: str


def _c(s: str) -> re.Pattern[str]:
    return re.compile(s, re.IGNORECASE)


# Each pattern matches one well-known injection vector. The `rationale` is
# what gets surfaced in the event log so a viewer can tell *why* a
# specific phrase tripped the guardrail.
PROMPT_INJECTION_PATTERNS: list[_Pattern] = [
    _Pattern(
        name="ignore_prior_instructions",
        regex=_c(r"\b(ignore|disregard|forget)\s+(?:all\s+|the\s+|your\s+|any\s+|previous\s+|prior\s+|above\s+|earlier\s+)*(instructions?|prompts?|rules?|system\s*prompt|context|directives?)\b"),
        rationale="user tried to override system instructions",
    ),
    _Pattern(
        name="reveal_system_prompt",
        regex=_c(r"\b(reveal|show|print|output|display|tell|give)\s+(?:me\s+)?(?:your\s+|the\s+|us\s+)?(system\s*prompt|initial\s*prompt|hidden\s*prompt|original\s*prompt)\b"),
        rationale="user tried to exfiltrate system prompt",
    ),
    _Pattern(
        name="role_override_now",
        regex=_c(r"\b(you\s+are\s+now|from\s+now\s+on,?\s+you|act\s+as|pretend\s+to\s+be|roleplay\s+as)\b"),
        rationale="user tried to override the assistant's role",
    ),
    _Pattern(
        name="role_message_injection",
        regex=_c(r"(^|\n)\s*(system|assistant|user)\s*:\s*"),
        rationale="user injected fake role-tagged messages",
    ),
    _Pattern(
        name="instruction_tag_injection",
        regex=_c(r"</?\s*(instructions?|system|prompt)\s*>"),
        rationale="user injected pseudo-XML instruction tags",
    ),
    _Pattern(
        name="markdown_instruction_header",
        regex=_c(r"(^|\n)\s*#{1,3}\s+(new\s+)?(instructions?|system|directive)"),
        rationale="user injected a markdown instruction header",
    ),
    _Pattern(
        name="exfiltration_data_request",
        regex=_c(r"\b(api[\s_-]*key|secret|password|token|credentials?)\b.*\b(reveal|show|print|output|tell\s+me|give\s+me)\b"),
        rationale="user asked to exfiltrate credentials",
    ),
    _Pattern(
        name="exfiltration_credentials_reveal",
        regex=_c(r"\b(reveal|show|print|output|tell\s+me|give\s+me)\b.*\b(api[\s_-]*key|secret|password|token|credentials?)\b"),
        rationale="user asked to exfiltrate credentials",
    ),
]


def detect_prompt_injection(text: str) -> list[_Pattern]:
    """Return the list of patterns that matched the text. Empty = clean."""
    if not text:
        return []
    return [p for p in PROMPT_INJECTION_PATTERNS if p.regex.search(text)]


def check_prompt_injection(text: str, guardrail_name: str = "prompt_injection_block") -> None:
    """Raise GuardrailBlocked on the first matching pattern.

    Snippet in the exception is the matching substring, not the whole
    text — keeps the event log compact and avoids logging long bodies.
    """
    matches = detect_prompt_injection(text)
    if not matches:
        return
    first = matches[0]
    m = first.regex.search(text)
    snippet = m.group(0) if m else text[:80]
    raise GuardrailBlocked(guardrail_name, first.name, snippet)
