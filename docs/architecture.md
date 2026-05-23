# Architecture

> Placeholder. To be filled with PlantUML or Mermaid diagrams once the pipeline is wired.

## Components

- **Agent orchestrator** (`src/agent/pipeline.py`) — drives the 5-step SEO pipeline.
- **State layer** (`src/state/`) — checkpoint, event log, resume.
- **Failure injection** (`src/failure_inject/`) — middleware for the gateway client that simulates failures.
- **TrueFoundry AI Gateway** (SaaS) — routing, fallback, guardrails, observability.
- **AWS Bedrock** (us-east-1) — 4 foundation models in priority chain.

## Failure modes mapped to recovery mechanisms

(see [failure-modes.md](failure-modes.md))

## Cedar policy mapping

(see [cedar-policy-mapping.md](cedar-policy-mapping.md))
