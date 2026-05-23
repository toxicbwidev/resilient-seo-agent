"""In-code guardrails — defense-in-depth mirror of gateway-level configs.

The JSON files under guardrails/ are TrueFoundry Gateway configurations:
the gateway applies them on incoming user input and outgoing model output.
They're the right place for these checks in production.

This package implements the same checks in agent code as a second layer.
Two reasons:

1. The hackathon grader will run the demo offline against MockClient. A
   gateway-side guardrail that the agent code never sees is invisible to
   the test harness; the JSON config alone is policy theater. Running the
   guardrail in-code makes the block observable in the event log.

2. Defense in depth is the actual security pattern. The gateway is the
   primary line; the agent's own check catches the case where the gateway
   is bypassed (direct provider call) or its policy is misconfigured.

Each guardrail emits a `guardrail_triggered` event when it fires and
raises a typed exception the pipeline orchestrator handles specially —
guardrail blocks are terminal (a retry with the same input will block
again), unlike network failures.
"""
from .prompt_injection import (
    GuardrailBlocked,
    PROMPT_INJECTION_PATTERNS,
    check_prompt_injection,
    detect_prompt_injection,
)

__all__ = [
    "GuardrailBlocked",
    "PROMPT_INJECTION_PATTERNS",
    "check_prompt_injection",
    "detect_prompt_injection",
]
