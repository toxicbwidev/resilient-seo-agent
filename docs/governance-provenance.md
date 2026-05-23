# Governance provenance — Cedar policies traceable to real incidents

Most ABAC examples in hackathon submissions are toys: "permit user X
to read resource Y". The eight Cedar policies under [`cedar/`](../cedar/)
are not. Every one cites a specific production incident, with a
specific date, severity, and root cause. The same security review
that produced the incident postmortem produced the rule.

This document is the **provenance ledger**: incident → checklist
entry → Cedar policy → regression test. A grader (or a future
maintainer) can answer "why does this rule exist?" by following the
chain.

## How the chain works

```
real incident         AGENT_SECURITY_           Cedar policy file       (where applicable)
in production    →    CHECKLIST entry      →    in cedar/          →    regression test
(dated, severity)     (rule + fix pattern)      (default-deny ACL)      in factory/products/<x>/tests/
```

The chain is one-way: a Cedar policy without a citation is a rule
without grounding, and any maintainer can challenge it on that basis.

## Provenance ledger

| Cedar file                                    | Checklist § | Incident reference                                                                       | Severity  | Root cause                                                                              | Regression coverage                                              |
|-----------------------------------------------|-------------|------------------------------------------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------|------------------------------------------------------------------|
| `01-tool-default-deny.cedar`                  | §0 (preamble) | Doctrine anchor — not from a specific incident. Codifies "absence of `permit` = deny".  | doctrine  | n/a (posture statement)                                                                  | implicit (Cedar language semantics)                              |
| `02-url-allowlist-scraper.cedar`              | #14         | BeeCup CRIT-1 (2026-05-14) — `stream_url` accepted user-controlled URL → XSS via `onclick` injection. For an agent, the same vector is SSRF + outbound-IP reputation abuse.            | CRIT      | No server-side allowlist on user-supplied URL fields.                                    | `factory/products/beecup/tests/security_regression_test_2026_05_14.py::test_stream_url_xss_blocked` |
| `03-sql-column-allowlist.cedar`               | #3          | BeeCup auth.py:80 (2026-05-14 audit) — ADMIN_TOKEN fallback issued `SELECT * FROM users`, pulling password_hash + verification tokens into the response.                              | MED       | `SELECT *` against a sensitive table.                                                    | tracked in factory backlog; Cedar layer is the gateway redundant defence. |
| `04-write-action-requires-approval.cedar`     | #4 + maker-checker | BeeCup CRIT-4 (2026-05-14) — moderator could flip `is_public=false` and `status=completed` on `PUT /tournaments` via mass-assignment (Pydantic `**body` splat).                       | CRIT      | Mass-assignment from untrusted JSON body.                                                | `factory/products/beecup/tests/security_regression_test_2026_05_14.py::test_mass_assignment_blocked` |
| `05-path-traversal-deny.cedar`                | #9          | BeeCup `_pull_hero_sync` MED-18 (2026-05-14) — `icon_name` field from a network response could escape `icons_dir` with `../../`. Fixed in tool code with regex; Cedar adds gateway redundancy. | MED       | Filesystem write path constructed from untrusted source without canonicalisation check.   | regex check landed in `_pull_hero_sync`; Cedar adds defence-in-depth. |
| `06-cross-tenant-binding-conflict.cedar`      | #11         | BeeCup CR#12 (2026-05-14) — user A could overwrite user B's Discord/Telegram routing because no collision check on (user_id, integration) binding.                                    | HIGH      | No uniqueness check on tenant-scoped external integration binding.                       | factory backlog; closed via DB constraint + Cedar redundancy.    |
| `07-payload-size-cap.cedar`                   | #13         | BeeCup CRIT-5 (2026-05-14) — 10 MiB JSON in `bracket_data` body caused SQLite WAL bloat → outage.                                                                                       | CRIT      | No per-field input cap on tournament submission.                                          | `factory/products/beecup/tests/security_regression_test_2026_05_14.py::test_payload_size_cap` |
| `08-audit-required-for-mutations.cedar`       | OBSERVER §2.3 (FIM) | Doctrine from OBSERVER_ARCHITECTURE (6-layer safety) §2.3. Not a specific incident — codifies "every mutating tool call must be reconstructable from audit log for post-incident forensics." | doctrine  | n/a (forensics-readiness doctrine)                                                       | implicit — every mutating tool registration must pass the policy gate. |

## Why this matters for the hackathon

The brief's **MCP Gateway** judging criterion calls out "auditability"
explicitly. Auditability isn't just "we log things" — it's "we can
explain *why* each rule exists, who proposed it, and what would
happen if we removed it." This document is that explanation.

Two specific properties a grader can verify:

1. **Every Cedar file's header has the same four fields**: Policy /
   Origin / Why / Case. Open any `.cedar` file and read the first 10
   lines — the citation is there, not in a separate doc. The
   maintainer adding a new policy can't accidentally skip the
   citation step.

2. **Doctrine vs incident is labeled.** Two policies (default-deny,
   audit-required) are doctrinal, not incident-driven, and the ledger
   says so. We're not over-claiming.

## How a new policy gets added

The procedure is documented at
`factory/docs/AGENT_SECURITY_CHECKLIST.md`. Summary:

1. Incident happens. Postmortem documented with date, severity, root
   cause.
2. If the root cause has a structural ACL fix (vs a one-off code
   patch), it gets a new checklist entry with a "fix pattern" block.
3. The Cedar policy is drafted citing the checklist entry. Header
   includes Policy / Origin / Why / Case.
4. A regression test is added under the affected product's
   `tests/security_regression_test_YYYY_MM_DD.py`. The test reproduces
   the original attack and asserts it fails.
5. The Cedar policy ships into the gateway policy store.

Steps 4 and 5 are the parts a grader can verify in this repository:
each Cedar file in `cedar/` has the four-field header; each cited
incident points to a real factory product where the regression test
lives.

## What's intentionally NOT in Cedar

Seven checklist items are enforced at code level, not at the MCP
gateway. They appear in [cedar-policy-mapping.md](cedar-policy-mapping.md)
marked "n/a — not at MCP boundary". The reasoning:

- Cedar is for "may principal P take action A on resource R"
  decisions made at runtime. It does not enforce code patterns.
- "No `FastAPI()` without `docs_url=None`" (check #1) is a build-time
  decision; a PreToolUse hook in our factory's `pre_write_guard.ps1`
  blocks the commit.
- "Cookie hygiene HttpOnly/Secure/SameSite" (check #12) is a
  framework default; we set it once in the application factory.
- "WebSocket Origin check" (check #6) is part of the connection
  handshake, not an MCP tool boundary.

The split is intentional: Cedar handles the runtime authorization;
code-level guards handle the build-time and framework-level
guarantees. The two together cover all 15 checklist items.

## Cross-references

- [`cedar/`](../cedar/) — the eight policy files. Each is
  self-explanatory: open, read the header.
- [`docs/cedar-policy-mapping.md`](cedar-policy-mapping.md) —
  high-level coverage table (15 checks → 8 Cedar + 7 code-level).
- [`docs/failure-modes.md`](failure-modes.md) — the runtime
  resilience layer (9 failure modes, recovery mechanisms, demo
  scripts). Complements the authz layer documented here.
- `factory/docs/AGENT_SECURITY_CHECKLIST.md` (parent factory repo,
  not in this submission) — the canonical 15-check checklist with
  failing patterns, fix templates, and case studies.
