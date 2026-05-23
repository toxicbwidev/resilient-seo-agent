# Failure modes and recovery mechanisms

Six distinct failure modes, six distinct recovery mechanisms. Each is reproducible via a script under `demos/`.

| # | Failure mode                       | Where it hits           | Recovery mechanism                                              | Demo script                       |
|---|------------------------------------|-------------------------|-----------------------------------------------------------------|-----------------------------------|
| 1 | Bedrock 429 rate limit             | Primary model invoke    | Priority-chain fallback to next Bedrock model                   | `demos/scenario-1-rate-limit.py`  |
| 2 | Provider outage (5xx, network)     | Primary model invoke    | Circuit breaker opens → route to fallback (different provider)  | `demos/scenario-2-outage.py`      |
| 3 | Slow response (timeout >30s)       | Any model invoke        | Timeout cancel → next provider in chain                         | `demos/scenario-3-timeout.py`     |
| 4 | MCP tool failure (5xx, malformed)  | Tool call               | Post-tool guardrail detects bad result → degraded-mode skip     | `demos/scenario-4-tool-fail.py`   |
| 5 | Prompt injection in user input     | Pipeline entry          | Input guardrail blocks (Enforce mode) → safe fallback prompt    | `demos/scenario-5-injection.py`   |
| 6 | Cascading multi-step failure       | 3 steps in sequence     | State preservation → resume from last checkpoint                | `demos/scenario-6-cascade.py`     |

## Recovery axes

- **Retry / fallback** — TrueFoundry routing handles 1–3 declaratively.
- **Guardrails** — TrueFoundry handles 4–5 via header-driven policies.
- **State preservation** — our own contribution handles 6 (agent-level concern; gateway does not own pipeline state).

## Observability

Every recovery action is visible in TrueFoundry Request Traces (OpenTelemetry spans):
- Span per LLM call shows: primary model attempted, error, fallback model used, total latency
- Span per guardrail check shows: guardrail name, action (block/redact/audit), latency

Screenshots from these traces are included in the demo video.
