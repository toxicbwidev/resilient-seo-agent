// Policy:  Tool calls that write/modify resources require an explicit approval flag
// Origin:  AGENT_SECURITY_CHECKLIST check #4 (mass-assignment) + general
//          maker-checker pattern from OBSERVER_ARCHITECTURE §2.1
// Why:     LLM-driven agents can be coerced (via prompt injection) into
//          performing destructive operations. Requiring an explicit approval
//          token on the resource means a separate code path (e.g. a maker-
//          checker LLM, or a human reviewer in production) must mark the
//          operation as approved before the gateway forwards it to the tool.
// Case:    BeeCup CRIT-4 (2026-05-14) — moderator could flip `is_public=false`
//          / `status=completed` via mass-assignment on PUT /tournaments. The
//          analogue for an agent is the LLM convincing itself to delete data.
//
// Resource: MCP tools where `action_class` includes "destructive" or "mutate".

forbid (
    principal,
    action == Action::"invoke",
    resource
) when {
    resource.action_class in ["destructive", "mutate"] &&
    !(resource.has_approval_token == true)
};
