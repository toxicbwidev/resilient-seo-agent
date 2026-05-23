# Resilient SEO Agent

> Submission for the **Resilient Agents Hackathon** by TrueFoundry + AWS Bedrock (June 1–7, 2026).

A production-grade resilient AI agent that keeps producing SEO content even when LLM providers fail. Built on TrueFoundry AI Gateway with AWS Bedrock, demonstrating six distinct recovery mechanisms across six failure modes.

## What it does

A multi-step SEO content pipeline for content marketers:

```
voice profile  →  keyword/intent research  →  outline drafting
              →  content writing  →  on-page optimization
```

Each step is an LLM call (different task class, different model) plus tool calls to external SEO data sources (SERP API, keyword DB, competitor scraper).

The pipeline survives:

| Failure mode                           | Recovery mechanism                                      |
| -------------------------------------- | ------------------------------------------------------- |
| Provider rate limit (HTTP 429)         | Priority-chain fallback to next Bedrock model           |
| Provider outage                        | Circuit breaker opens, route to fallback model          |
| Slow response (timeout >30s)           | Timeout cancel → next provider in chain                 |
| MCP tool failure                       | Post-tool guardrail detects error → degraded-mode skip  |
| Prompt injection in user input         | Input guardrail blocks → safe fallback prompt           |
| Cascading multi-step failure           | State preservation → resume from last checkpoint        |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  SEO Agent (Python)                                 │
│  ├── 5-step pipeline orchestrator                   │
│  ├── State preservation (checkpoint after step)     │  ◄── DIFFERENTIATOR
│  ├── Failure injection harness (for demo/testing)   │  ◄── DIFFERENTIATOR
│  └── Recovery playbook (6 distinct mechanisms)      │  ◄── DIFFERENTIATOR
└──────────────────┬──────────────────────────────────┘
                   │ Chat Completions API (OpenAI-compatible)
┌──────────────────▼──────────────────────────────────┐
│  TrueFoundry AI Gateway (SaaS)                      │
│  ├── Routing: TaskType → priority chain             │
│  │     Claude Sonnet 4.6  ▶  Mistral Large 3        │
│  │            ▶  Llama 4 Maverick  ▶  Cohere R+     │
│  ├── Guardrails (headers per request)               │
│  │     • LLM input:  PII, prompt injection           │
│  │     • LLM output: secrets, content moderation     │
│  │     • MCP pre:    SQL sanitizer, URL whitelist    │
│  │     • MCP post:   code safety, PII in results     │
│  ├── Cedar policies (AGENT_SECURITY_CHECKLIST)      │  ◄── DIFFERENTIATOR
│  ├── Semantic caching                                │
│  ├── Per-user/model/app rate limits                  │
│  └── Request Traces UI (OpenTelemetry)               │
└──────────────────┬──────────────────────────────────┘
                   ▼
   AWS Bedrock  (Anthropic / Mistral / Meta / Cohere)
```

## Differentiators

1. **Production-grade state preservation.** Append-only event log + crash-only writes + checkpoint-per-step. Ported from a working pattern proven across 100+ cross-provider agent delegations.
2. **AGENT_SECURITY_CHECKLIST → Cedar policies.** 14 real-incident-derived rules translated to Cedar policy language for default-deny MCP tool access. Not toy examples — production rules.
3. **Real product, real user.** SEO content for content marketers, not a weather-demo agent.
4. **Six distinct recovery mechanisms** on six failure modes. Most submissions show one retry pattern on everything.
5. **Failure injection harness as a deliverable.** Judges can re-run any of the six scenarios themselves.

## Repository layout

```
src/
  agent/             — pipeline orchestrator, step implementations
  state/             — checkpoint, event log, resume logic
  guardrails_runner/ — local guardrail invocation (mirrors gateway)
  failure_inject/    — failure simulation harness
gateway-config/
  *.yaml             — TrueFoundry manifests (not committed if contain secrets)
guardrails/
  *.json             — guardrail policy configs (PII, prompt injection, etc.)
cedar/
  *.cedar            — Cedar ABAC policies for MCP tool access
demos/
  scenario-1-rate-limit.py
  scenario-2-outage.py
  ... (6 scripts, one per failure mode)
docs/
  architecture.md
  failure-modes.md
  cedar-policy-mapping.md
tests/
  test_state.py
  test_recovery.py
```

## Quick start

```bash
# 1. Setup
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your TrueFoundry API key

# 3. Run pipeline
python -m src.agent.pipeline --topic "best running shoes 2026"

# 4. Run failure-injection demo
python demos/scenario-1-rate-limit.py
```

## License

MIT (planned). Hackathon submission.

## Acknowledgments

- TrueFoundry for the AI Gateway, MCP Gateway, and Guardrails infrastructure
- AWS for Bedrock and hackathon credits
- Resilience patterns adapted from banking (maker-checker), aviation (FIM/Tripwire), exchanges (pre-trade compliance), and SCADA (shadow staging)
