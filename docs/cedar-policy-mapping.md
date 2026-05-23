# Cedar policy mapping

Cedar policies in [`cedar/`](../cedar/) implement default-deny access control for MCP tools, derived from the AGENT_SECURITY_CHECKLIST — 14 production-derived rules from real past security incidents.

## Mapping table

| Check # | Original rule (paraphrased)                                  | Cedar policy file                  | Status |
|---------|--------------------------------------------------------------|------------------------------------|--------|
| 1       | No FastAPI() without docs_url=None                           | n/a — code-level, not runtime ACL  | —      |
| 2       | No `SELECT u.*` without explicit column allowlist            | `sql-column-allowlist.cedar`       | TODO   |
| 3       | No `**body` unpacking into ORM update without field filter   | `orm-field-filter.cedar`           | TODO   |
| 4       | No StaticFiles mount on admin paths                          | `static-mount-deny.cedar`          | TODO   |
| 5       | No JOIN users without auth context                           | `users-join-with-auth.cedar`       | TODO   |
| 6       | No path traversal via user-supplied path                     | `path-traversal-deny.cedar`        | TODO   |
| 7       | No session UPDATE without ceiling check                      | `session-update-ceiling.cedar`     | TODO   |
| 8       | Whitelist of allowed scraper URL domains                     | `scraper-url-whitelist.cedar`      | TODO   |
| 9       | Rate-limit per-tool, per-identity                            | `tool-rate-limit.cedar`            | TODO   |
| 10      | Read-only vs write-capable tool role split                   | `tool-role-rw-split.cedar`         | TODO   |
| 11      | Audit log required for every destructive action              | `audit-required.cedar`             | TODO   |
| 12      | No DELETE without explicit approval flag                     | `delete-requires-approval.cedar`   | TODO   |
| 13      | No HTTP without TLS (egress)                                 | `egress-tls-only.cedar`            | TODO   |
| 14      | Secrets never returned to LLM in raw form                    | `secrets-redact.cedar`             | TODO   |

## Why this matters

These are not toy examples. Each rule is the codification of a real past incident where the absence of that check led to data loss, unauthorized access, or service disruption. Translating them to Cedar gives:

- Declarative enforcement (no developer can forget the check)
- Audit trail at gateway level (every decision logged)
- Default-deny posture (new tools start without access, must be explicitly granted)
- Composable rules (e.g. URL whitelist + rate limit + role split applied together)

## Authoring conventions

- One file per logical rule (easier to review, easier to disable selectively)
- Each file starts with a header comment citing the original incident
- Tests in `tests/cedar/test_<policy>.py` exercise allow/deny boundary cases
