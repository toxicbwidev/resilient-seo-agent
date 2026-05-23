# Failure modes and recovery mechanisms

Nine failure modes — six required by the hackathon brief, three the
brief implies but doesn't enumerate. Each one has its own demo script
so a grader can re-run it independently.

The hackathon brief calls out six failure categories: rate limits,
provider outages, slow responses, tool failures, bad intermediate
outputs, and cascading errors. We cover all six, and we split "bad
intermediate outputs" into the two cases it actually contains — *bad
shape* (malformed JSON) and *bad content* (well-formed but wrong) —
because they're caught by different layers. We add two more that the
brief implies but doesn't list explicitly: prompt-injection attacks on
user-supplied input, and zombie steps that hang silently.

| #  | Failure mode                          | Where it hits         | Recovery mechanism                                                     | Demo script                                       |
|----|---------------------------------------|-----------------------|------------------------------------------------------------------------|---------------------------------------------------|
| 1  | Provider rate limit (HTTP 429)        | LLM call              | Retry within step; in prod, gateway routes to next-priority model      | `demos/scenario_1_rate_limit.py`                  |
| 2  | Provider outage (5xx / network down)  | LLM call              | Same retry path; gateway circuit-breaker routes to fallback provider   | `demos/scenario_2_provider_outage.py`             |
| 3  | Slow response                         | LLM call              | Watchdog cancels; gateway-level timeout routes to next provider        | `demos/scenario_3_slow_response.py`               |
| 4  | MCP tool failure (5xx)                | Tool call             | Retry; post-tool guardrail rejects junk results before they propagate  | `demos/scenario_4_tool_failure.py`                |
| 5  | Corrupted output (malformed JSON)     | LLM response parsing  | `parse_output` raises; retry path runs                                 | `demos/scenario_5_corrupted_response.py`          |
| 6  | Cascading failure across steps        | Multiple steps        | State preservation: every step checkpointed; resume from last good     | `demos/scenario_6_cascading.py`                   |
| 7  | Semantic hallucination (NEW)          | LLM response          | Per-step semantic postcondition catches well-formed but unusable JSON  | `demos/scenario_7_semantic_hallucination.py`      |
| 8  | Prompt injection in user input (NEW)  | Pipeline entry        | In-code input guardrail blocks before the call — terminal abort        | `demos/scenario_8_prompt_injection.py`            |
| 9  | Zombie step (silent hang) (NEW)       | LLM call              | Watchdog timer raises `ZombieStepDetected`; retry path picks up        | `demos/scenario_9_zombie_hang.py`                 |

## Why 7, 8, and 9 are not just nice-to-haves

**Scenario 7 — semantic hallucination.** Scenario 5 catches *malformed*
JSON: the response is unparseable. That's the easy case. The harder
case is when the model returns valid JSON with `[]` for keywords or an
"article" that's three sentences long. Without a semantic
postcondition, the pipeline cheerfully proceeds and produces an
unusable output. This is what the hackathon brief actually means by
"bad intermediate outputs" — not malformed text, but content the next
step can't use.

**Scenario 8 — prompt injection in user input.** The brief lists
"blocking unsafe inputs" as a guardrails requirement. Eight guardrail
JSON configs sit under `guardrails/`, but the JSON configs run on the
gateway and are invisible to a grader running the demo offline against
the mock client. The in-code guardrail at `src/guardrails/` mirrors
the same checks at the agent layer so a demo run observably blocks the
attack — and so the guardrails still fire if the gateway is bypassed
or its policy is misconfigured (defense in depth).

**Scenario 9 — zombie step.** A retry loop only fires on exceptions.
If the model provider stops responding mid-stream — socket open,
connection alive, zero bytes flowing — the pipeline appears to run but
never makes progress. The watchdog wraps each model call with a
wall-clock timer. A trip converts the silent hang into
`ZombieStepDetected`, which the retry loop handles like any other
failure.

## Recovery axes

- **Retry / fallback.** Scenarios 1–4 ride the standard retry budget.
  In production, the TrueFoundry AI Gateway handles cross-provider
  routing declaratively; in offline mode the agent retries against the
  mock client.
- **Output verification.** Scenarios 5 and 7 are caught at the agent
  layer — `parse_output` for shape, `postcondition` for semantics.
- **Input guardrail.** Scenario 8 is blocked before the model ever
  sees the prompt. Terminal — retry would block again.
- **Watchdog.** Scenario 9 converts silent hangs into observable
  failures. Trade-off: the worker thread leaks; state is preserved so
  the pipeline resumes cleanly on a process restart.
- **State preservation.** Scenario 6 demonstrates the differentiator:
  no recovery mechanism inside a step saves the run, but the agent
  also doesn't end up in an undefined state — state on disk reflects
  exactly what completed, and an operator can resume from there.

## Observability

Every recovery action is visible in two places:

1. **Local event log** (`event_log.jsonl` per pipeline): every
   `step_started`, `step_failed`, `step_succeeded`, `fallback_used`,
   `guardrail_triggered`, `checkpoint_written`, `pipeline_completed`
   is on disk and re-runnable.
2. **TrueFoundry Request Traces** (when running against the live
   gateway): OpenTelemetry spans show primary model attempted, error,
   fallback model used, total latency, and guardrail action.
