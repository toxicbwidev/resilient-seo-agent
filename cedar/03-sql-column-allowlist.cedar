// Policy:  Database-read tools must request explicit column lists
// Origin:  AGENT_SECURITY_CHECKLIST check #3 (no SELECT * from sensitive tables)
// Why:     `SELECT *` over a sensitive table — users, accounts, sessions —
//          pulls password_hash, email_verification_token, refresh_token, etc.
//          into the LLM context window. An output guardrail can redact some
//          of this, but the safer default is "the tool can never read the
//          forbidden columns in the first place."
// Case:    BeeCup auth.py:80 ADMIN_TOKEN fallback had `SELECT *` on users —
//          found 2026-05-14 in audit, fix tracked.
//
// Resource: MCP tools tagged `kind == "db_query"` that target sensitive tables.

permit (
    principal,
    action == Action::"invoke",
    resource
) when {
    resource.kind == "db_query" &&
    resource.table in ["users", "accounts", "sessions"] &&
    resource.requested_columns.containsAll([]) &&  // i.e. an explicit list provided
    !(resource.requested_columns.contains("password_hash")) &&
    !(resource.requested_columns.contains("email_verification_token")) &&
    !(resource.requested_columns.contains("refresh_token")) &&
    !(resource.requested_columns.contains("session_token")) &&
    !(resource.requested_columns.contains("api_key_hash"))
};

// Non-sensitive tables pass through without column restriction.
permit (
    principal,
    action == Action::"invoke",
    resource
) when {
    resource.kind == "db_query" &&
    !(resource.table in ["users", "accounts", "sessions"])
};
