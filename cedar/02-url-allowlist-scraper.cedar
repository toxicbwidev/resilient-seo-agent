// Policy:  Scraper tools may only fetch from approved domains
// Origin:  AGENT_SECURITY_CHECKLIST check #14 (URL/redirect fields — server-side regex allowlist)
// Why:     Free-form URL inputs reach a renderer or an HTTP fetcher. Without
//          a server-side allowlist, a prompt-injected user input can drive
//          the scraper to internal IPs (SSRF) or to malicious endpoints
//          that abuse our outbound IP reputation.
// Case:    BeeCup CRIT-1 (2026-05-14) — stream_url XSS via onclick injection.
//          For an agent, the equivalent is SSRF + reputation abuse.
//
// Resource: MCP tools tagged `kind == "scraper"` — e.g. serp_scraper,
//           competitor_scraper, web_fetch. SEO research tools that take a URL.

permit (
    principal,
    action == Action::"invoke",
    resource
) when {
    resource.kind == "scraper" &&
    resource.target_host in [
        "google.com",
        "www.google.com",
        "bing.com",
        "www.bing.com",
        "duckduckgo.com",
        "serpapi.com",
        "api.serpapi.com",
        "ahrefs.com",
        "api.ahrefs.com"
    ]
};
