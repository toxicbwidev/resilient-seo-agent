# Failure injection demos

Six runnable scripts, one per failure mode. Each:

1. Starts the pipeline with a real seed prompt
2. Injects the failure at the right pipeline stage
3. Captures the recovery path in `event_log.jsonl`
4. Prints a colored summary of: failure → recovery action → final output

## Usage

```bash
python demos/scenario-1-rate-limit.py
```

Each script is self-contained — independent state dir, independent event log. Re-running cleans the previous state.

## Scenarios

See [`../docs/failure-modes.md`](../docs/failure-modes.md) for the full table.

| Scenario | What it proves |
|---|---|
| 1 — rate limit  | Gateway routes to next provider when primary returns 429 |
| 2 — outage      | Circuit breaker opens after repeated failures |
| 3 — timeout     | Slow primary is cancelled, fallback responds |
| 4 — tool fail   | Bad tool result is caught post-tool, pipeline continues degraded |
| 5 — injection   | Malicious prompt is blocked at gateway input guardrail |
| 6 — cascade     | 3-step failure leaves checkpoint, resume reads it, finishes job |
