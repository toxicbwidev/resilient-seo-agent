"""Tests for the per-step semantic postconditions.

Each postcondition has a happy case (passes) and one or two failure cases
matching the kinds of "valid JSON but bad content" that real LLMs return.
Plus an end-to-end test that runs the pipeline with a hallucinating
MockClient and verifies the retry path closes the gap.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.client import MockClient
from src.agent.pipeline import run_pipeline
from src.agent.self_test import (
    SelfTestFailed,
    check_draft,
    check_keyword,
    check_optimize,
    check_outline,
    check_voice,
)
from src.state import StateStore


# --- check_voice -----------------------------------------------------------

def test_voice_happy_path() -> None:
    check_voice({
        "tone": "casual_authoritative",
        "vocabulary_level": "intermediate",
        "sentence_length": "medium",
        "avoid_words": ["synergy"],
    })


def test_voice_rejects_empty_tone() -> None:
    with pytest.raises(SelfTestFailed) as ex:
        check_voice({"tone": "", "vocabulary_level": "intermediate", "sentence_length": "medium"})
    assert "tone" in ex.value.reason


def test_voice_rejects_invalid_vocab_level() -> None:
    with pytest.raises(SelfTestFailed) as ex:
        check_voice({"tone": "x", "vocabulary_level": "guru", "sentence_length": "medium"})
    assert "vocabulary_level" in ex.value.reason


# --- check_keyword ---------------------------------------------------------

def _kw(s: str, intent: str = "informational") -> dict:
    return {"keyword": s, "intent": intent, "estimated_volume": "high"}


def test_keyword_happy_path() -> None:
    check_keyword([_kw(f"keyword {i}") for i in range(5)])


def test_keyword_rejects_empty_list() -> None:
    with pytest.raises(SelfTestFailed) as ex:
        check_keyword([])
    assert "at least 5" in ex.value.reason


def test_keyword_rejects_too_few() -> None:
    with pytest.raises(SelfTestFailed) as ex:
        check_keyword([_kw("a"), _kw("b")])
    assert "at least 5" in ex.value.reason


def test_keyword_rejects_duplicates() -> None:
    with pytest.raises(SelfTestFailed) as ex:
        check_keyword([_kw(f"same") for _ in range(5)])
    assert "duplicate" in ex.value.reason.lower()


# --- check_outline ---------------------------------------------------------

def test_outline_happy_path() -> None:
    check_outline({
        "h1": "Best Running Shoes",
        "sections": [
            {"h2": "Methodology", "target_keyword": "x"},
            {"h2": "Top Picks", "target_keyword": "x"},
            {"h2": "Sizing", "target_keyword": "x"},
        ],
    })


def test_outline_rejects_too_few_sections() -> None:
    with pytest.raises(SelfTestFailed):
        check_outline({"h1": "Title", "sections": [{"h2": "only one"}]})


# --- check_draft -----------------------------------------------------------

def test_draft_happy_path() -> None:
    text = "## Section\n\n" + ("word " * 350)
    check_draft(text)


def test_draft_rejects_too_short() -> None:
    with pytest.raises(SelfTestFailed) as ex:
        check_draft("## Section\n\nshort article")
    assert "too short" in ex.value.reason.lower()


def test_draft_rejects_no_h2() -> None:
    with pytest.raises(SelfTestFailed):
        check_draft("just text " * 350)


# --- check_optimize --------------------------------------------------------

def test_optimize_happy_path() -> None:
    check_optimize({
        "article": "A " * 200,  # 400 chars
        "meta_description": "A reasonable-length meta description for the article.",
        "internal_links": ["one", "two"],
    })


def test_optimize_rejects_short_meta() -> None:
    with pytest.raises(SelfTestFailed):
        check_optimize({
            "article": "A " * 200,
            "meta_description": "tiny",
            "internal_links": [],
        })


def test_optimize_rejects_long_meta() -> None:
    with pytest.raises(SelfTestFailed):
        check_optimize({
            "article": "A " * 200,
            "meta_description": "x" * 200,
            "internal_links": [],
        })


# --- end-to-end: pipeline catches hallucination ---------------------------

def test_pipeline_recovers_from_hallucinated_keyword_step(tmp_path: Path) -> None:
    """First KEYWORD call returns [] (passes parse_output but fails check_keyword).
    Retry returns normal response. Pipeline completes."""
    client = MockClient(hallucinate_calls=[2])  # call 2 = keyword first attempt
    store = StateStore(tmp_path / "state")
    state = run_pipeline(client, store, "self-test-recovery", "test topic")

    assert state.is_done(5)
    assert state.completed_steps == ["voice", "keyword", "outline", "draft", "optimize"]
    # Event log should show one SelfTestFailed and then success
    evs = list(store.read_events("self-test-recovery"))
    self_test_fails = [e for e in evs if e.get("error_type") == "SelfTestFailed"]
    assert len(self_test_fails) == 1
    assert self_test_fails[0]["step_name"] == "keyword"


def test_pipeline_aborts_when_hallucinations_exhaust_retries(tmp_path: Path) -> None:
    """All KEYWORD calls hallucinate. Pipeline exhausts retries, aborts, state preserved."""
    # max_retries=2 means up to 3 attempts. Hallucinate calls 2, 3, 4
    # (keyword attempts 1, 2, 3). Voice succeeds on call 1.
    client = MockClient(hallucinate_calls=[2, 3, 4])
    store = StateStore(tmp_path / "state")

    with pytest.raises(Exception):  # SelfTestFailed propagates after exhausted retries
        run_pipeline(client, store, "self-test-exhaust", "test topic")

    state = store.load_latest("self-test-exhaust")
    assert state is not None
    assert state.completed_steps == ["voice"]  # only voice got through
    assert state.current_step == 1  # stuck on keyword
