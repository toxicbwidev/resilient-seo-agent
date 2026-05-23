# Guardrail policies

JSON policies attached to LLM/MCP calls via TrueFoundry headers.

## Application points

| Header                              | Files in this dir                    |
|-------------------------------------|--------------------------------------|
| `llm_input_guardrails`              | `input-pii-redact.json`, `input-prompt-injection.json` |
| `llm_output_guardrails`             | `output-secrets-detect.json`, `output-content-moderation.json` |
| `mcp_tool_pre_invoke_guardrails`    | `mcp-sql-sanitizer.json`, `mcp-url-whitelist.json` |
| `mcp_tool_post_invoke_guardrails`   | `mcp-code-safety.json`, `mcp-pii-results.json` |

## Modes

- Input validation runs **parallel** with model call → zero latency on happy path
- Mutation policies (PII redact, output strip) run synchronously

## Enforcement strategy

- Prod scenarios: `Enforce But Ignore On Error` (guardrail bug doesn't break pipeline)
- Experimental: `Audit` (log only, don't block)
