"""Tests for FailoverClient — agent-side cross-model failover."""
from __future__ import annotations

from src.agent.failover_client import (
    AllModelsExhausted,
    FailoverClient,
    _is_failover_trigger,
    current_step_var,
)


class _RecordingClient:
    """Stub GatewayClient that records every .complete() call.

    `responses` is a list of either "OK <text>" strings to return or
    exception instances to raise (in call order). When the list is
    exhausted further calls raise IndexError to fail loudly.
    """

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []  # (model_pref, model_override)

    def complete(
        self,
        model_pref: str,
        system: str,
        user: str,
        model_override: str | None = None,
    ) -> str:
        self.calls.append((model_pref, model_override or ""))
        if not self._responses:
            raise IndexError("RecordingClient: out of canned responses")
        nxt = self._responses.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


# --- Synthetic exception types to drive the failover trigger classification.
# We can't import openai.RateLimitError etc. without paying the dep cost, so
# we name our test exceptions to match the class names the classifier checks.
class RateLimitError(Exception):
    pass


class BadRequestError(Exception):
    pass


class PermissionDeniedError(Exception):
    pass


class APIConnectionError(Exception):
    pass


# Sentinel for "this exception name should NOT trigger failover."
class CallerDomainError(Exception):
    pass


def test_first_model_succeeds_no_failover():
    inner = _RecordingClient(responses=["hello"])
    fb = FailoverClient(inner=inner, model_chain=["a", "b", "c"])
    assert fb.complete("pref", "sys", "user") == "hello"
    assert inner.calls == [("pref", "a")]


def test_first_fails_second_succeeds():
    inner = _RecordingClient(responses=[RateLimitError("429"), "ok"])
    events: list[tuple] = []

    def cb(frm, to, exc):
        events.append((frm, to, type(exc).__name__))

    fb = FailoverClient(inner=inner, model_chain=["a", "b"], on_fallback=cb)
    assert fb.complete("pref", "sys", "user") == "ok"
    assert [call[1] for call in inner.calls] == ["a", "b"]
    assert events == [("a", "b", "RateLimitError")]


def test_all_models_fail_raises_exhausted():
    inner = _RecordingClient(
        responses=[
            RateLimitError("rl1"),
            BadRequestError("country block"),
            APIConnectionError("conn"),
        ]
    )
    fb = FailoverClient(inner=inner, model_chain=["a", "b", "c"])
    try:
        fb.complete("pref", "sys", "user")
    except AllModelsExhausted as e:
        assert e.chain == ["a", "b", "c"]
        assert isinstance(e.last_exc, APIConnectionError)
        assert e.__cause__ is e.last_exc
    else:
        raise AssertionError("expected AllModelsExhausted")


def test_non_failover_exception_propagates_immediately():
    """A CallerDomainError (GuardrailBlocked-class) must NOT trigger failover.

    The chain should stop on the first model and re-raise. Pipeline (or
    other caller) handles those types itself.
    """
    inner = _RecordingClient(responses=[CallerDomainError("guardrail block")])
    fb = FailoverClient(inner=inner, model_chain=["a", "b", "c"])
    try:
        fb.complete("pref", "sys", "user")
    except CallerDomainError:
        pass
    else:
        raise AssertionError("expected CallerDomainError to propagate")
    # Only the first model was tried — failover NOT triggered.
    assert inner.calls == [("pref", "a")]


def test_explicit_model_override_bypasses_chain():
    """If caller passes model_override, FailoverClient honors it directly."""
    inner = _RecordingClient(responses=["direct"])
    fb = FailoverClient(inner=inner, model_chain=["a", "b", "c"])
    out = fb.complete("pref", "sys", "user", model_override="explicit-model")
    assert out == "direct"
    # Chain not used; the explicit override is passed through verbatim.
    assert inner.calls == [("pref", "explicit-model")]


def test_empty_chain_rejected():
    inner = _RecordingClient(responses=[])
    try:
        FailoverClient(inner=inner, model_chain=[])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty chain")


def test_fallback_callback_only_fires_when_next_exists():
    """The fallback callback fires for transitions A→B, B→C — not after C
    fails (there's nowhere to go). Otherwise we'd double-emit fallback +
    AllModelsExhausted for the same final failure.
    """
    events: list = []
    inner = _RecordingClient(
        responses=[
            RateLimitError("r1"),  # a fails → emit a→b
            RateLimitError("r2"),  # b fails → emit b→c
            RateLimitError("r3"),  # c fails → DO NOT emit (no next), raise
        ]
    )
    fb = FailoverClient(
        inner=inner,
        model_chain=["a", "b", "c"],
        on_fallback=lambda frm, to, exc: events.append((frm, to)),
    )
    try:
        fb.complete("pref", "sys", "user")
    except AllModelsExhausted:
        pass
    assert events == [("a", "b"), ("b", "c")]


def test_callback_exception_does_not_break_inference():
    """Telemetry callback raising must never break the inference path."""
    inner = _RecordingClient(responses=[RateLimitError("r"), "ok"])

    def broken_callback(frm, to, exc):
        raise RuntimeError("telemetry blew up")

    fb = FailoverClient(
        inner=inner, model_chain=["a", "b"], on_fallback=broken_callback
    )
    # Should still succeed via fallback to "b" even though callback raised.
    assert fb.complete("pref", "sys", "user") == "ok"


def test_classifier_recognizes_common_provider_errors():
    # Sanity check on the name-based classifier — it's our only guard
    # against expanding the chain to caller-domain errors by accident.
    assert _is_failover_trigger(RateLimitError("x")) is True
    assert _is_failover_trigger(BadRequestError("x")) is True
    assert _is_failover_trigger(PermissionDeniedError("x")) is True
    assert _is_failover_trigger(APIConnectionError("x")) is True
    assert _is_failover_trigger(CallerDomainError("x")) is False
    assert _is_failover_trigger(KeyboardInterrupt()) is False
    # SystemExit must propagate cleanly (not be caught by the chain).
    assert _is_failover_trigger(SystemExit()) is False


def test_current_step_var_contextvar_default_is_none():
    # Sanity check on the contextvar default; pipeline sets it before
    # calling .complete(), failover_client's callback reads it.
    assert current_step_var.get() is None
