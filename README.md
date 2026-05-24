# Resilient SEO Agent

> Submission for the **Resilient Agents Hackathon** by TrueFoundry + AWS Bedrock (June 1–7, 2026).

A production-grade resilient AI agent that keeps producing SEO content even when LLM providers fail. Built on TrueFoundry AI Gateway with AWS Bedrock. Nine reproducible failure scenarios, nine distinct recovery mechanisms — covering every failure category the hackathon brief calls out, plus three the brief implies but doesn't enumerate (semantic hallucination, prompt injection, zombie state).

## What it does

A multi-step SEO content pipeline for content marketers:

```
voice profile  →  keyword/intent research  →  outline drafting
              →  content writing  →  on-page optimization
```

Each step is an LLM call (different task class, different model) plus tool calls to external SEO data sources (SERP API, keyword DB, competitor scraper).

The pipeline survives:

| #  | Failure mode                          | Recovery mechanism                                                  |
| -- | ------------------------------------- | ------------------------------------------------------------------- |
| 1  | Provider rate limit (HTTP 429)        | Retry within step; gateway routes to next-priority model            |
| 2  | Provider outage                       | Retry; gateway circuit-breaker routes to fallback provider          |
| 3  | Slow response                         | Watchdog cancels; gateway timeout routes to next provider           |
| 4  | MCP tool failure                      | Retry; post-tool guardrail rejects junk results                     |
| 5  | Corrupted output (malformed JSON)     | `parse_output` raises; retry path                                   |
| 6  | Cascading multi-step failure          | State preservation → resume from last checkpoint                    |
| 7  | Semantic hallucination *(new)*        | Per-step postcondition catches well-formed but unusable JSON        |
| 8  | Prompt injection in user input *(new)*| In-code input guardrail blocks before the call (terminal abort)     |
| 9  | Zombie step / silent hang *(new)*     | Watchdog raises `ZombieStepDetected`; retry path picks up           |

See `docs/failure-modes.md` for the full rationale on why 7/8/9 are not just nice-to-haves.

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
2. **AGENT_SECURITY_CHECKLIST → Cedar policies, with provenance.** 14 real-incident-derived rules translated to Cedar policy language for default-deny MCP tool access. Every policy cites its originating incident with date and severity — see [`docs/governance-provenance.md`](docs/governance-provenance.md). Not toy examples — production rules.
3. **Real product, real user.** SEO content for content marketers, not a weather-demo agent.
4. **Nine distinct recovery mechanisms** across nine failure modes. Most submissions show one retry pattern on everything; we split "bad intermediate outputs" into structural and semantic, add prompt-injection blocking, and add a watchdog for zombie state.
5. **Failure injection harness as a deliverable.** Judges can re-run any of the nine scenarios themselves with `python demos/scenario_<N>_*.py`.
6. **In-code guardrails mirror gateway configs.** The 8 JSON guardrail policies under `guardrails/` are the production layer; `src/guardrails/` runs the same checks in the agent so a demo run observably blocks attacks even against the mock client.
7. **Watchdog for zombie steps.** Retry loops only fire on exceptions. A model that goes silent mid-stream needs a wall-clock timer — `src/agent/watchdog.py` converts silent hangs into observable failures.
8. **Chaos engineering, not stress loops.** Six hypothesis-driven experiments in Chaos Toolkit-shape JSON under [`chaos/experiments/`](chaos/experiments/). 280 pipelines run across all six experiments, **100% state integrity, 0% crashes, 6/6 PASS** — see [`chaos/results/SUMMARY.md`](chaos/results/SUMMARY.md). Reproducible with `python -m chaos run-all`.
9. **Orchestrator-choice rationale.** The brief leaves the agent orchestration framework open; we explain why raw Python over TF Workflows / LangGraph / CrewAI / AutoGen in [`docs/orchestrator-choice.md`](docs/orchestrator-choice.md), pre-empting the "why not LangGraph" question.
10. **Agent-side cross-model failover, not a gateway routing rule.** The "resilient" part of "resilient agent" lives in the agent code: [`src/agent/failover_client.py`](src/agent/failover_client.py) wraps any `GatewayClient` with a configurable model chain. On rate-limit / outage / country-block / timeout it transparently advances to the next model and emits a `FallbackUsed` event so the decision is auditable. A real run on 2026-05-24 exercised this through TrueFoundry AI Gateway against a chain of 5 models (Bedrock × 2 → Gemini → Mistral × 2) — the live event log with 25 fallback transitions is committed at [`submission_artifacts/live-run-event-log.jsonl`](submission_artifacts/live-run-event-log.jsonl) (see [`submission_artifacts/README.md`](submission_artifacts/README.md)).

## Repository layout

```
src/
  agent/             — pipeline orchestrator, step implementations,
                       per-step semantic postconditions (self_test.py),
                       watchdog for zombie detection
  state/             — checkpoint, append-only event log, resume logic
  guardrails/        — in-code prompt-injection guardrail (defense in
                       depth — gateway is primary, this is secondary)
  failure_inject/    — failure simulation harness (5 exception types,
                       6 preset scenarios)
gateway-config/
  *.yaml             — TrueFoundry manifests (gitignored if they
                       carry secrets)
guardrails/
  *.json             — gateway-side guardrail configs (PII, prompt
                       injection, secrets, content moderation, MCP)
cedar/
  *.cedar            — Cedar ABAC policies for MCP tool access (8
                       policies from AGENT_SECURITY_CHECKLIST)
demos/
  scenario_1_rate_limit.py
  scenario_2_provider_outage.py
  scenario_3_slow_response.py
  scenario_4_tool_failure.py
  scenario_5_corrupted_response.py
  scenario_6_cascading.py
  scenario_7_semantic_hallucination.py
  scenario_8_prompt_injection.py
  scenario_9_zombie_hang.py
docs/
  failure-modes.md         — 9-row table with the full rationale
  cedar-policy-mapping.md  — checklist → policy mapping (15 checks)
chaos/
  experiments/             — 6 Chaos Toolkit-shape JSON experiments
  results/SUMMARY.md       — committed run summary, 6/6 PASS, 280 pipes
  results/*.json           — per-run JSONs (gitignored)
  random_client.py         — probability-based failure injector
  injectors.py             — chaos experiment entry points
  runner.py                — Chaos Toolkit-format experiment runner
tests/
  test_state.py            — 7 tests
  test_failure_inject.py   — 12 tests
  test_pipeline.py         — 5 tests
  test_self_test.py        — 17 tests (semantic postconditions)
  test_guardrails.py       — 16 tests (prompt-injection patterns)
  test_watchdog.py         — 6 tests (zombie detection)
  test_chaos.py            — 10 tests (framework + injector determinism)
```

**Test count: 83/83 passing. Chaos: 6/6 experiments PASS across 280 pipelines.**

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
