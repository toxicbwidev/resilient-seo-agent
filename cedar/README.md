# Cedar policies

Default-deny ABAC policies for MCP tool access. Translated from the AGENT_SECURITY_CHECKLIST (14 production-derived rules).

See [`../docs/cedar-policy-mapping.md`](../docs/cedar-policy-mapping.md) for the rule-to-file mapping.

## Authoring conventions

Each file:
1. Header comment naming the original rule and the incident it derives from
2. Single Cedar `permit` or `forbid` statement
3. Companion test in `tests/cedar/`

## Order of evaluation

Cedar uses **default-deny** — if no `permit` matches, the action is denied. `forbid` statements override `permit`.

## Validation

```bash
python scripts/validate-cedar.py cedar/*.cedar
```
