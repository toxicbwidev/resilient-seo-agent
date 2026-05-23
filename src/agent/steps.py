"""The five-step SEO content pipeline.

Each Step encapsulates: which routing class to ask the gateway for, what
system prompt to use, how to build the user message from the running
state, and how to parse / validate the model's response. Steps are pure
data; the orchestrator in pipeline.py drives them.

The order matters: each step consumes outputs of every earlier step.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ._json import extract_json


@dataclass
class Step:
    name: str
    model_pref: str
    system_prompt: str
    build_user_prompt: Callable[[dict[str, Any]], str]
    parse_output: Callable[[str], Any]


def _voice_user(outputs: dict[str, Any]) -> str:
    return (
        f'Define the brand voice for an SEO blog about: "{outputs["topic"]}".\n'
        f"Return JSON only with keys: tone (string), vocabulary_level "
        f"(beginner|intermediate|expert), sentence_length (short|medium|long), "
        f"avoid_words (array of strings)."
    )


def _keyword_user(outputs: dict[str, Any]) -> str:
    return (
        f'Topic: {outputs["topic"]}\nVoice: {outputs["voice"]}\n\n'
        "Return a JSON array of 10 keyword objects. Each object has: keyword "
        "(string), intent (informational|commercial|navigational|transactional), "
        "estimated_volume (low|medium|high)."
    )


def _outline_user(outputs: dict[str, Any]) -> str:
    return (
        f'Topic: {outputs["topic"]}\nVoice: {outputs["voice"]}\n'
        f'Keywords: {outputs["keyword"]}\n\n'
        "Write a JSON outline with keys: h1 (string), sections (array of objects "
        "with h2 and target_keyword), intro_hook (string, 1-2 sentences)."
    )


def _draft_user(outputs: dict[str, Any]) -> str:
    return (
        f'Outline: {outputs["outline"]}\nVoice: {outputs["voice"]}\n\n'
        "Write the full article body in markdown, ~800 words. Match the voice. "
        "Use each section's target keyword in its H2 and within the section body."
    )


def _optimize_user(outputs: dict[str, Any]) -> str:
    return (
        f'Article:\n{outputs["draft"]}\n\nKeywords: {outputs["keyword"]}\n\n'
        "Optimize the article. Return JSON with keys: article (the SEO-revised "
        "markdown), meta_description (max 160 chars), internal_links "
        "(array of suggested anchor texts)."
    )


VOICE = Step(
    name="voice",
    model_pref="creative",
    system_prompt="You output brand voice as compact JSON. No commentary.",
    build_user_prompt=_voice_user,
    parse_output=extract_json,
)

KEYWORD = Step(
    name="keyword",
    model_pref="classifier",
    system_prompt="You are an SEO keyword researcher. JSON only.",
    build_user_prompt=_keyword_user,
    parse_output=extract_json,
)

OUTLINE = Step(
    name="outline",
    model_pref="writer",
    system_prompt="You draft SEO blog outlines. JSON only.",
    build_user_prompt=_outline_user,
    parse_output=extract_json,
)

DRAFT = Step(
    name="draft",
    model_pref="creative",
    system_prompt=(
        "You are a senior SEO content writer. Output markdown only — no "
        "commentary before or after the article body."
    ),
    build_user_prompt=_draft_user,
    parse_output=lambda raw: raw.strip(),  # markdown stays as text
)

OPTIMIZE = Step(
    name="optimize",
    model_pref="writer",
    system_prompt="You are an SEO optimization specialist. JSON only.",
    build_user_prompt=_optimize_user,
    parse_output=extract_json,
)

PIPELINE_STEPS: list[Step] = [VOICE, KEYWORD, OUTLINE, DRAFT, OPTIMIZE]
