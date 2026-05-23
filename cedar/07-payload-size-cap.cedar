// Policy:  Tool inputs must respect per-field byte caps
// Origin:  AGENT_SECURITY_CHECKLIST check #13 (input size caps on every text field)
// Why:     A tool that accepts large freeform text without a cap is a DoS
//          surface (WAL bloat, memory blowup, downstream queue saturation).
//          The agent itself can be coerced into producing a 100 MB prompt
//          via a feedback loop. Cap at the gateway, fail-closed.
// Case:    BeeCup CRIT-5 (2026-05-14) — 10 MiB JSON in bracket_data caused
//          SQLite WAL bloat. Closed.
//
// Resource: any MCP tool with a `payload_size_bytes` attribute.

forbid (
    principal,
    action == Action::"invoke",
    resource
) when {
    resource.payload_size_bytes > 1048576  // 1 MiB hard cap
};

// Stricter cap on database-write tools — most legitimate writes are <64 KiB
// and the larger amount usually indicates a bug or attack.
forbid (
    principal,
    action == Action::"invoke",
    resource
) when {
    resource.kind == "db_write" &&
    resource.payload_size_bytes > 65536  // 64 KiB
};
