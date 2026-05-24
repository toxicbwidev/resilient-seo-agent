"""Agent-side cross-model failover.

Wraps any GatewayClient and on each .complete() call iterates a configured
chain of (provider/model) strings. On a failover-triggering exception
(rate limit, provider outage, timeout, country block, etc.) we move to
the next model in the chain. If every model fails, we raise
AllModelsExhausted with the last underlying exception as __cause__.

Why this lives in the agent, not in a TrueFoundry routing rule:
the hackathon brief asks for a 'resilient agent' — resilience belongs
to the agent code, not a gateway feature flag. The gateway is the
transport; the agent makes the failover decision and emits the
FallbackUsed telemetry that makes that decision auditable.

Wiring telemetry: the on_fallback callback receives
(from_model, to_model, exception). For pipeline integration the
callback also reads `current_step_var` (a contextvars.ContextVar set
by pipeline._run_one_step before it calls .complete) so the emitted
FallbackUsed event can name the originating step.

Exception classification: we trigger failover on errors that mean
"this provider is unhealthy for this request, try another." We do NOT
trigger on GuardrailBlocked, SelfTestFailed, parse errors, or
KeyboardInterrupt — those are caller-domain concerns and propagate
unchanged. Classification is by exception class name to avoid hard
dependencies on openai/httpx packages at import time.
"""
from __future__ import annotations

import contextvars
from typing import Callable

from .client import GatewayClient


current_step_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "failover_current_step", default=None
)


# Exception class names that mean "model unhealthy for this request, try
# next one in the chain." Listed by string name to avoid importing every
# upstream SDK at this module's import time.
_FAILOVER_TRIGGER_NAMES = frozenset(
    {
        # openai SDK errors (TF Gateway returns these wrapped)
        "RateLimitError",
        "APIError",
        "APIStatusError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
        "BadRequestError",  # Bedrock returns 400 with body "Operation not allowed" for country block
        "AuthenticationError",  # provider creds rotated mid-run — fail over, not pipeline-abort
        "PermissionDeniedError",
        # our injected failure subclasses (failure_inject/exceptions.py)
        "RateLimit",
        "Outage",
        "Timeout",
        "ToolFailure",
        # watchdog
        "ZombieStepDetected",
        # httpx low-level
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "TimeoutException",
        # generic
        "TimeoutError",
    }
)


def _is_failover_trigger(exc: BaseException) -> bool:
    """Should this exception cause us to advance to the next model?"""
    return type(exc).__name__ in _FAILOVER_TRIGGER_NAMES


class AllModelsExhausted(RuntimeError):
    """Every model in the chain raised a failover-triggering exception.

    Carries the chain that was tried and the last underlying exception
    (also available via __cause__). Re-raised by FailoverClient when no
    model survives.
    """

    def __init__(self, chain: list[str], last_exc: BaseException) -> None:
        super().__init__(
            f"all {len(chain)} models in chain exhausted; last error: "
            f"{type(last_exc).__name__}: {last_exc}"
        )
        self.chain = list(chain)
        self.last_exc = last_exc


class FailoverClient:
    """Cross-model failover wrapper for a GatewayClient.

    On each .complete() call we iterate `model_chain` in order, passing
    each model as the model_override to the wrapped client. The first
    success returns. Failover-triggering exceptions skip to the next
    model and (if a callback is configured) emit a fallback event with
    the from/to model names and the underlying exception.

    If a caller explicitly passes model_override to .complete(), we
    honor it directly without using the chain — this is the "I know
    what I want, don't fall over" escape hatch (tests, ad-hoc smokes).
    """

    def __init__(
        self,
        inner: GatewayClient,
        model_chain: list[str],
        on_fallback: Callable[[str, str, BaseException], None] | None = None,
    ) -> None:
        if not model_chain:
            raise ValueError("model_chain cannot be empty")
        self._inner = inner
        self._chain = list(model_chain)
        self._on_fallback = on_fallback

    @property
    def model_chain(self) -> list[str]:
        return list(self._chain)

    def complete(
        self,
        model_pref: str,
        system: str,
        user: str,
        model_override: str | None = None,
    ) -> str:
        if model_override is not None:
            # Explicit override — bypass chain. Caller knows what they want.
            return self._inner.complete(
                model_pref, system, user, model_override=model_override
            )

        last_exc: BaseException | None = None
        for idx, model in enumerate(self._chain):
            try:
                return self._inner.complete(
                    model_pref, system, user, model_override=model
                )
            except Exception as exc:
                if not _is_failover_trigger(exc):
                    # Not our concern — guardrail block, parse error,
                    # postcondition fail, etc. Let pipeline handle it.
                    raise
                last_exc = exc
                # If there's a next model, log the transition before retrying.
                if idx + 1 < len(self._chain) and self._on_fallback is not None:
                    try:
                        self._on_fallback(model, self._chain[idx + 1], exc)
                    except Exception:
                        # Telemetry must never break inference.
                        pass
                continue

        # Chain exhausted — surface a typed exception so callers can
        # distinguish "this provider is bad" from "every provider is bad."
        assert last_exc is not None
        raise AllModelsExhausted(self._chain, last_exc) from last_exc
