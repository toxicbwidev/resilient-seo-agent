// Policy:  Binding an external integration must not collide with another tenant's binding
// Origin:  AGENT_SECURITY_CHECKLIST check #11 (cross-tenant integration binding)
// Why:     If a tool can bind a Slack channel, a webhook, or a Telegram chat
//          to "this agent run", and there is no collision check, agent A can
//          hijack agent B's notification channel. For SEO use cases this maps
//          to e.g. publishing to a CMS where the target page is already
//          claimed by another pipeline.
// Case:    BeeCup CR#12 (2026-05-14) — user A could overwrite user B's
//          Discord/Telegram routing. Closed.
//
// Resource: MCP tools tagged `kind == "bind"` (publish_to_cms, schedule_post,
//           webhook_subscribe, etc.).

forbid (
    principal,
    action == Action::"invoke",
    resource
) when {
    resource.kind == "bind" &&
    resource.target_already_bound_to_other_principal == true
};
