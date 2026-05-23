// Policy:  Mutating tool calls must opt into audit-log capture
// Origin:  AGENT_SECURITY_CHECKLIST §"How to use this checklist", and
//          OBSERVER_ARCHITECTURE §2.3 (File Integrity Monitoring) doctrine
// Why:     Forensics after an incident depends on having an audit trail of
//          who did what when. The gateway can centralise this — but only if
//          mutating tools explicitly request audit_required=true in their
//          resource registration. Default-deny makes the omission a build-
//          time error rather than a silent loss of evidence.
//
// Resource: MCP tools with action_class "destructive" or "mutate".

forbid (
    principal,
    action == Action::"invoke",
    resource
) when {
    resource.action_class in ["destructive", "mutate"] &&
    !(resource.audit_required == true)
};
