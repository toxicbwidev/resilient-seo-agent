// Policy:  Filesystem-touching tools must operate on validated paths
// Origin:  AGENT_SECURITY_CHECKLIST check #9 (path-traversal on file write)
// Why:     Any tool that takes a filename or path from LLM output is one
//          `../../etc/passwd` away from arbitrary read or write. The defence
//          must be at the gateway (declarative) AND in the tool code
//          (programmatic) — defence in depth.
// Case:    BeeCup `_pull_hero_sync` MED-18 (2026-05-14) — icon_name from
//          network could escape the icons_dir. Fixed with regex; this Cedar
//          policy is the gateway-level redundant check.
//
// Resource: MCP tools tagged `kind == "fs_write"` or `kind == "fs_read"`.

forbid (
    principal,
    action == Action::"invoke",
    resource
) when {
    (resource.kind == "fs_write" || resource.kind == "fs_read") &&
    (
        resource.path like "*..*"
        || resource.path like "/etc/*"
        || resource.path like "/root/*"
        || resource.path like "C:\\Windows\\*"
        || resource.path like "/proc/*"
        || resource.path like "/sys/*"
    )
};

// Permit reads/writes within the agent's sandboxed working area.
permit (
    principal,
    action == Action::"invoke",
    resource
) when {
    (resource.kind == "fs_write" || resource.kind == "fs_read") &&
    (
        resource.path like ".session_state/*"
        || resource.path like "checkpoints/*"
        || resource.path like "outputs/*"
    )
};
