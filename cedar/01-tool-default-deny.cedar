// Policy:  default-deny posture
// Origin:  AGENT_SECURITY_CHECKLIST §0 (implicit doctrine, "Source of truth" preamble)
// Why:     Cedar is default-deny by language design — if no `permit` matches,
//          the action is denied. This file makes the intent explicit so a
//          reviewer reading cedar/ alone knows the system is allowlist, not
//          denylist. Removing this file changes nothing operationally; it
//          exists for documentation and to anchor reviewer mental models.
//
// Coverage: All MCP tool invocations against any agent identity. Specific
//           `permit` rules in 02–08 grant narrow exceptions for known-good
//           combinations of (principal, action, resource).

// Intentionally empty — Cedar denies by default. Specific permits live
// in the numbered files in this directory. New permits must cite an
// AGENT_SECURITY_CHECKLIST entry or a documented case study.
