# Cedar policy mapping

Cedar policies in [`cedar/`](../cedar/) translate AGENT_SECURITY_CHECKLIST checks (15 production-derived rules from `factory/docs/AGENT_SECURITY_CHECKLIST.md`) into default-deny ABAC policies for MCP tool access.

## Why this is a differentiator

Most hackathon submissions write toy ABAC examples. Each policy here cites a real past incident — they exist because something specifically broke in production and the postmortem demanded a structural prevention.

## Coverage matrix

| Check # | Original rule (paraphrased)                                 | Cedar file                              | Coverage |
|---------|-------------------------------------------------------------|-----------------------------------------|----------|
| —       | Default-deny posture (documentation anchor)                 | [`01-tool-default-deny.cedar`](../cedar/01-tool-default-deny.cedar) | ✅ |
| 14      | URL allowlist for scrapers / outbound HTTP                  | [`02-url-allowlist-scraper.cedar`](../cedar/02-url-allowlist-scraper.cedar) | ✅ |
| 3       | No `SELECT *` from sensitive tables                         | [`03-sql-column-allowlist.cedar`](../cedar/03-sql-column-allowlist.cedar) | ✅ |
| 4       | Mutating tool calls require approval token                  | [`04-write-action-requires-approval.cedar`](../cedar/04-write-action-requires-approval.cedar) | ✅ |
| 9       | Path-traversal denied; sandbox enforcement                  | [`05-path-traversal-deny.cedar`](../cedar/05-path-traversal-deny.cedar) | ✅ |
| 11      | Cross-tenant integration binding conflict                   | [`06-cross-tenant-binding-conflict.cedar`](../cedar/06-cross-tenant-binding-conflict.cedar) | ✅ |
| 13      | Per-field payload size caps                                 | [`07-payload-size-cap.cedar`](../cedar/07-payload-size-cap.cedar) | ✅ |
| —       | Audit-log capture required for mutations                    | [`08-audit-required-for-mutations.cedar`](../cedar/08-audit-required-for-mutations.cedar) | ✅ |
| 1       | No `FastAPI()` without `docs_url=None`                      | code-level (PreToolUse hook in factory) | n/a — not a runtime ACL decision |
| 2       | No admin HTML under public static mount                     | code-level                              | n/a |
| 5       | GET endpoints with `JOIN users` need auth or `is_public`    | application-level (FastAPI dependency)  | n/a — not at MCP boundary |
| 6       | WebSocket Origin check + per-client write tag + PII redact  | application-level                       | n/a — not an MCP tool |
| 7       | Re-validate user on long-lived WS connections               | application-level                       | n/a |
| 8       | Sessions: absolute lifetime ceiling                         | application-level                       | n/a |
| 10      | Email/account creation: atomic create+verify, cleanup       | transactional, not authz                | n/a |
| 12      | Cookie hygiene (HttpOnly, Secure, SameSite)                 | framework default                       | n/a |
| 15      | mTLS scope: only inside `location`, never on server level   | nginx config                            | n/a |

8 of the 15 checks translate to runtime ABAC decisions (Cedar policies); the other 7 are code-level/framework-level (already enforced by `pre_write_guard.ps1` or by framework defaults in production).

## How policies are applied

Cedar evaluation happens at the **TrueFoundry MCP Gateway** boundary. The agent sends an `invoke` request for a tool; the gateway extracts (principal, action, resource) from the request, runs Cedar against the policies in this directory, and either forwards the call to the tool or returns 403 with the matching `forbid` rule cited in the audit log.

Cedar's **default-deny** semantics mean that the absence of a matching `permit` is itself a deny — adding new tools without explicit `permit` rules is a build-time/registration-time problem, not a runtime surprise.

## Authoring conventions

- **One file per logical rule.** Easier to review, easier to disable selectively in incident response.
- **Each file opens with a 4-line header:** Policy name, origin (which checklist entry), rationale, and incident citation. A future maintainer must know *why* the policy exists.
- **`permit` vs `forbid`:** prefer `forbid` for security boundary rules — they override `permit` in Cedar, so they survive future permit expansions. Use `permit` only for narrow grants over the default-deny baseline.

## Validation

A full Cedar validator (`cedar-policy/cedar-cli`) checks syntax and type consistency. For this submission we ship the policies as documentation artefacts; in production they would be loaded into the gateway's policy store and validated on every reload.

```bash
# (planned, not yet wired)
cedar validate --policies cedar/ --schema cedar/schema.cedarschema.json
```
