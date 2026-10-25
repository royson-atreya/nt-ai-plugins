# Pre-flight before any browser run (run-web, retest)

Stop at the first failure and tell the user what to fix.

1. **Base URL.** Take the configured staging URL the skill shows. If it is empty or still a literal `${…}`, use the "Staging base URL" from the session context (SessionStart banner); else `https://staging-dashboard.naditarangini.com`. The host must be `staging-dashboard.naditarangini.com`; otherwise stop and ask the user to fix `staging_base_url` (/plugin → Installed → nt-qa-testing → Configure options).
2. **Playwright.** Load `mcp__plugin_playwright_playwright__browser_navigate` with ToolSearch (`select:` query). If it is not available, stop: the playwright plugin must be installed and connected (`/mcp` shows its status).
3. **Selection.** Count the selected cases by status. If none is `Ready` (all Skipped/Blocked, or the given ids do not exist), list why and stop. Name requested ids that are not Ready.
4. **Roles preview.** Compare the roles the selected cases need with "Test roles configured" in the session context. Cases for roles not listed will be Blocked at run time; say how many.
5. **Timestamp.** Get it with `date +%Y%m%d-%H%M` when a folder name needs one.
6. **Confirm.** One AskUserQuestion: "Run N cases on <base URL> as <roles>? <M will be Blocked: college not configured.> They create QA-AUTO dummy records on staging." Options: run / cancel.

## Abort handling after web-runner

- If no case reached `state: executed`, show the abort reason and stop; do not run result-checker.
- Otherwise run result-checker as usual and put the abort reason at the top of the hand-back.
