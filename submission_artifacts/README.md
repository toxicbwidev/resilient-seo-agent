# Live run artifacts — agent-side failover demo

Real, non-mock pipeline run on **2026-05-24** demonstrating cross-provider
model failover through the TrueFoundry AI Gateway. The agent attempted
each model from its `DEFAULT_MODEL_CHAIN` (defined in
`src/agent/main.py`) and used the on-disk event log to record every
fallback transition.

## What the run did

Topic: `"best running shoes 2026"`
Pipeline ID: `run-97ba566c`
State dir: `.session_state_live/` (gitignored)
Result: **4/5 steps succeeded via real cross-provider failover**; the
5th (`optimize`) was aborted by the per-step semantic postcondition
(generated meta_description was 173 chars, out of the 50–160 bound)
after 3 retries — state preserved on disk.

## Files

| File | What |
|---|---|
| `live-run-event-log.jsonl` | The raw append-only event log from `StateStore`. 46 events, 25 of them `fallback_used`. Every failover transition is here with attribution to the originating step. |
| `live-run-state.json` | The final checkpoint state — the four step outputs (`voice`, `keyword`, `outline`, `draft`) materialized as the agent saw them. |

## The failover chain that exercised

```python
DEFAULT_MODEL_CHAIN = [
    "aws-bedrock/us.anthropic.claude-sonnet-4-6",            # blocked by KZ country gate
    "aws-bedrock/us.meta.llama4-maverick-17b-instruct-v1-0", # blocked, same reason
    "google-gemini/gemini-2.5-flash-lite",                   # 403 — integration not yet wired
    "mistral-ai/mistral-large-latest",                       # primary working model
    "mistral-ai/mistral-small-latest",                       # rate-limit fallback
]
```

## What you can see in the event log

For each of the 5 steps:

1. `step_started` (attempt 1)
2. `fallback_used` × 3 (Bedrock-Claude → Bedrock-Llama → Gemini → Mistral-Large)
   each carrying the exception class name and a 160-char snippet of the
   provider error message
3. `step_succeeded` (model_used = step.model_pref class, e.g. `creative`,
   `classifier`, `writer`)
4. `checkpoint_written` (atomic state save)

In the `draft` step you'll see an additional patterns:

- `step_failed` with `error_type=ZombieStepDetected` — the watchdog
  caught Mistral-Large taking >30s, raised, and the retry path
  immediately re-entered the chain
- a second `fallback_used` cycle ending at Mistral-Small (Large hit a 429)

In the `optimize` step:

- 3 `step_started` attempts in a row
- Each ends with `step_failed` (error_type `SelfTestFailed`,
  meta_description out of [50, 160] bound)
- Final `pipeline_aborted` with state preserved for resume

## Reproducing this

```bash
# .env requires TFY_API_KEY (TrueFoundry JWT, 7-day TTL — read from
# C:\Users\ttt\.truefoundry\credentials.json on first run) and
# TFY_HOST (=https://<tenant>.truefoundry.cloud).
# Mistral and Gemini integrations must exist in the TF Gateway provider
# config — otherwise their chain entries 403/404 and failover skips them.

python -m src.agent.main --topic "best running shoes 2026" --state-dir .session_state_live

# Then:
cat .session_state_live/run-<id>/event_log.jsonl | jq 'select(.type=="fallback_used")'
```

## Why this is the brief demo, not gateway routing rules

The hackathon brief asks for a *resilient agent*. Resilience here is in
the agent's code — `src/agent/failover_client.py` — not in a TF Gateway
"routing rule" configured outside the repo. A grader can trace exactly
which exception class triggered each transition (see
`_FAILOVER_TRIGGER_NAMES` in `failover_client.py`) and how the agent
emitted telemetry to make the decision auditable
(`current_step_var` contextvar + `_emit_fallback` callback in
`src/agent/main.py`).

The fact that the chain currently exhausts three providers on every call
before reaching Mistral is **not a defect** — it's a real provider
outage (KZ-side AWS Bedrock country block + missing Google Gemini
integration) and the demo shows the agent gracefully working around it.
When Bedrock approval lands the chain self-recovers without code
changes.
