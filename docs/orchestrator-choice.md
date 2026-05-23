# Why raw Python orchestration?

The hackathon brief lists the required stack — AWS Bedrock, TrueFoundry
AI Gateway, MCP Gateway, Guardrails — but says nothing about which
**agent orchestration framework** to use. That's a real degree of
freedom in the design space, and this document explains the choice we
made and why.

**Short version:** we orchestrate with a 150-line Python loop
(`src/agent/pipeline.py`) and own our own state/retry/watchdog/
guardrail layers explicitly. We considered TrueFoundry Workflows,
LangGraph, CrewAI, and AutoGen; we passed on all of them. The
reasoning is below.

## Trade-off matrix

| Criterion                                | TF Workflows (Flyte)    | LangGraph              | CrewAI                  | AutoGen                | Raw Python (ours)    |
|------------------------------------------|-------------------------|------------------------|-------------------------|------------------------|----------------------|
| Resilience primitives built in           | per-task retry, timeout | conditional edges      | task delegation         | conversational retry   | explicit, in-repo    |
| State persistence model                  | Flyte runtime           | LangGraph checkpointer | implicit per-run        | conversation history   | atomic JSON + JSONL  |
| Deployment overhead                      | requires Flyte cluster  | none                   | none                    | none                   | none                 |
| Offline-testable (no cloud, no LLM key)  | no                      | partial                | no                      | no                     | yes (MockClient)     |
| Demo grader can reproduce                | hard                    | medium                 | hard                    | medium                 | trivial              |
| Resilience patterns visible in source    | hidden in runtime       | partial                | hidden                  | hidden                 | every line           |
| Vendor lock-in for the resilience layer  | high (Flyte)            | medium                 | medium                  | medium                 | none                 |
| Headline differentiator on judging       | "we used TF Workflows"  | "we used LangGraph"    | "we used CrewAI"        | "we used AutoGen"      | "show me the bug"    |

## Why each "no"

**TrueFoundry Workflows.** The on-page primitives are `@workflow`,
`@task`, `MapTask`, `ConditionalTask`, `Cron`. Useful when your
workload is heterogeneous and you want a managed runtime to schedule
containers across a cluster. Our workload is one Python process making
five sequential LLM calls. Adopting Workflows would mean: (1) deploy
to a Flyte cluster, (2) lose the ability to run the demo offline (AWS
Bedrock approval still pending — see the parent README), (3) pay for
the runtime in latency, (4) hide our resilience patterns behind
Flyte's retry/timeout config so a grader has to look in two places.
For a five-step pipeline the cost outweighs the benefit. We'd revisit
if the SEO pipeline grew to dozens of heterogeneous tasks.

**LangGraph.** Strong for stateful conversational agents with
branching dialog flows. Our pipeline is linear; the "graph" is a list.
The LangGraph checkpointer is a fine state primitive but introduces
LangChain as a dependency for what we get from 200 lines of
state.py. Adopting LangGraph would also move our retry/guardrail
logic into LangGraph idioms (`add_conditional_edges`,
`set_finish_point`), which makes the resilience patterns less
inspectable. Verdict: pay LangChain's whole dependency surface for
sugar we don't need.

**CrewAI.** Optimized for multi-agent collaboration ("planner",
"writer", "critic"). Our agent is single. CrewAI's task delegation
model assumes agents discover the right tool; we know which API to
call. The added abstraction layer hides exactly the failure modes
the hackathon brief asks us to demonstrate.

**AutoGen.** Conversational multi-agent, similar verdict to CrewAI
for our use case. Notably good for evolving research workflows;
overkill for a structured five-step content pipeline.

## What we get from raw Python

1. **Every recovery mechanism is in the repo, not the framework.**
   When a grader asks "how does this handle a slow response," the
   answer is `src/agent/watchdog.py` plus `src/agent/pipeline.py:90`.
   No "consult the LangGraph docs."

2. **Offline-testable.** `MockClient` substitutes for any provider.
   The six chaos experiments under `chaos/experiments/` run in five
   seconds on a laptop. A grader can reproduce them without an AWS
   account.

3. **State is just a file.** `pipeline_state.json` per pipeline, plus
   `event_log.jsonl`. `cat` works. `jq` works. No "open the
   LangGraph state inspector."

4. **No vendor lock.** Resilience patterns ship as a Python package
   anyone can import. If we later move to a Flyte workflow or a
   LangGraph orchestrator, our state/watchdog/guardrail layers come
   along unchanged.

5. **Honest about size.** The orchestrator is small because the
   problem is small. Adopting a framework would be performative size
   inflation, not actual capability.

## Where a framework would be the right call

- More than ~20 steps with non-trivial fanout / branching.
- Multiple agents with delegation (CrewAI / AutoGen territory).
- Branching conversational flow with user-in-the-loop (LangGraph).
- Heterogeneous compute (Python + Spark + container batch) where you
  want the runtime to handle scheduling (TrueFoundry Workflows /
  Flyte).
- Cron-style scheduled execution at production scale where the
  runtime owns retries across crashes (TF Workflows / Airflow).

None of these are the SEO content pipeline. The framework choice
should follow the workload, not the other way around.

## Honest counter-argument

Adopting TrueFoundry Workflows would have scored on the
"we used the platform end-to-end" axis a grader might apply. We
considered adding a thin `@workflow` wrapper around `run_pipeline`
just to demonstrate the integration, but decided against: it would be
performative usage, not resilience contribution, and would lose us
the offline-testable property that lets the chaos suite reproduce
without AWS access. The Cedar policies (`cedar/*.cedar`) and
guardrail configs (`guardrails/*.json`) already demonstrate full TF
stack integration on the dimensions that map to the judging criteria.
