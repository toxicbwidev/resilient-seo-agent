"""Per-step semantic postconditions.

Hackathon requirement: "bad intermediate outputs" must be handled. The
parse_output functions in steps.py only catch *structural* badness — a
response that isn't valid JSON, or markdown that's empty. They do not
catch *semantic* badness: a well-formed JSON array with zero items, an
"article" that's three sentences long, a meta_description that's blank.

This module defines postconditions that run after parse_output. They
look at the parsed value and assert the kind of properties a content
marketer would actually care about. A postcondition failure is treated
like any other step failure: the pipeline retries within its budget.
After exhausted retries, state is preserved on disk so a human can
inspect what the model kept hallucinating.

The thresholds are intentionally generous — the goal is to catch
obvious degradation (empty arrays, two-word drafts), not to enforce
quality. A real product would tune these per step and per model.
"""
from __future__ import annotations

from typing import Any


class SelfTestFailed(RuntimeError):
    """Raised when a step's output passes parse_output but fails its
    semantic postcondition.

    Carries the step name and the human-readable reason so the event log
    in event_log.jsonl tells a viewer exactly what was wrong.
    """

    def __init__(self, step_name: str, reason: str) -> None:
        super().__init__(f"step {step_name!r} failed self-test: {reason}")
        self.step_name = step_name
        self.reason = reason


# Postcondition functions: take the parsed output, raise SelfTestFailed
# if the value isn't usable. Step name is bound in steps.py at the
# Step dataclass level so the error message names the offending step.


def _require(cond: bool, step_name: str, reason: str) -> None:
    if not cond:
        raise SelfTestFailed(step_name, reason)


def check_voice(output: Any) -> None:
    step = "voice"
    _require(isinstance(output, dict), step, "expected dict, got " + type(output).__name__)
    tone = output.get("tone")
    _require(isinstance(tone, str) and len(tone.strip()) > 0, step, "tone is empty")
    level = output.get("vocabulary_level")
    _require(
        level in {"beginner", "intermediate", "expert"},
        step,
        f"vocabulary_level={level!r} not one of beginner/intermediate/expert",
    )
    sl = output.get("sentence_length")
    _require(
        sl in {"short", "medium", "long"},
        step,
        f"sentence_length={sl!r} not one of short/medium/long",
    )


def check_keyword(output: Any) -> None:
    step = "keyword"
    _require(isinstance(output, list), step, "expected list, got " + type(output).__name__)
    _require(len(output) >= 5, step, f"need at least 5 keywords, got {len(output)}")
    seen: set[str] = set()
    for i, kw in enumerate(output):
        _require(isinstance(kw, dict), step, f"keyword[{i}] is not a dict")
        s = kw.get("keyword", "")
        _require(
            isinstance(s, str) and len(s.strip()) >= 3,
            step,
            f"keyword[{i}].keyword is empty or too short: {s!r}",
        )
        _require(s.lower() not in seen, step, f"duplicate keyword: {s!r}")
        seen.add(s.lower())
        intent = kw.get("intent")
        _require(
            intent in {"informational", "commercial", "navigational", "transactional"},
            step,
            f"keyword[{i}].intent={intent!r} not in {{informational, commercial, navigational, transactional}}",
        )


def check_outline(output: Any) -> None:
    step = "outline"
    _require(isinstance(output, dict), step, "expected dict")
    h1 = output.get("h1", "")
    _require(isinstance(h1, str) and len(h1.strip()) >= 5, step, f"h1 too short: {h1!r}")
    sections = output.get("sections", [])
    _require(isinstance(sections, list), step, "sections is not a list")
    _require(len(sections) >= 3, step, f"need at least 3 sections, got {len(sections)}")
    for i, sec in enumerate(sections):
        _require(isinstance(sec, dict), step, f"sections[{i}] is not a dict")
        h2 = sec.get("h2", "")
        _require(isinstance(h2, str) and len(h2.strip()) >= 3, step, f"sections[{i}].h2 empty")


def check_draft(output: Any) -> None:
    step = "draft"
    _require(isinstance(output, str), step, "expected markdown string")
    word_count = len(output.split())
    _require(word_count >= 300, step, f"draft too short: {word_count} words, need >=300")
    # Look for at least one H2 — a real article has section headers.
    _require(
        "\n## " in output or output.startswith("## "),
        step,
        "no H2 section headers found in draft",
    )


def check_optimize(output: Any) -> None:
    step = "optimize"
    _require(isinstance(output, dict), step, "expected dict")
    meta = output.get("meta_description", "")
    _require(isinstance(meta, str), step, "meta_description is not a string")
    _require(
        50 <= len(meta) <= 160,
        step,
        f"meta_description length {len(meta)} out of 50..160",
    )
    article = output.get("article", "")
    _require(isinstance(article, str) and len(article) >= 200, step, "article too short")
    links = output.get("internal_links", [])
    _require(isinstance(links, list), step, "internal_links is not a list")


# Public mapping consumed by steps.py to attach the right check to each Step.
POSTCONDITIONS = {
    "voice": check_voice,
    "keyword": check_keyword,
    "outline": check_outline,
    "draft": check_draft,
    "optimize": check_optimize,
}
