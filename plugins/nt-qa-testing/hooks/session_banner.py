#!/usr/bin/env python3
"""SessionStart: list nt-qa-testing commands and which test roles are configured, only under ~/atreya-ai.

Shows configured yes/no per role, never a value.
"""
import json
import os
import re
import sys

sys.dont_write_bytecode = True

WORKSPACE = os.path.realpath(os.path.expanduser(os.environ.get("NT_WORKSPACE", "~/atreya-ai")))
STAGING = {"staging-dashboard.naditarangini.com", "staging-api.ashoka.world"}
ROLES = ("doctor", "admin", "patient", "college")

try:
    data = json.load(sys.stdin)
except ValueError:
    data = {}
cwd = os.path.realpath(data.get("cwd") or os.getcwd())
if not (cwd == WORKSPACE or cwd.startswith(WORKSPACE + os.sep)):
    sys.exit(0)


def opt(key):
    v = os.environ.get(f"CLAUDE_PLUGIN_OPTION_{key.upper()}", "")
    return "" if v.startswith("${") else v


base = opt("staging_base_url") or "https://staging-dashboard.naditarangini.com"
host = re.sub(r"(?i)^https?://", "", base).split("/", 1)[0].lower()
ready = [r for r in ROLES if opt(f"{r}_username") and opt(f"{r}_password")]
missing = [r for r in ROLES if r not in ready]

lines = [
    "nt-qa-testing (web staging only; output to ~/atreya-ai/nt-docs/qa/<id>)",
    "  /nt-qa-testing:plan <task|bug|module>   scope from nt-docs spec (or your bug report)",
    "  /nt-qa-testing:cases [id]               numbered test cases, bug repro first",
    "  /nt-qa-testing:run-web [id]             Playwright run + screenshots + evidence check",
    "  /nt-qa-testing:report [id]              pass/fail report + workbook CSV",
    "  /nt-qa-testing:retest <bug-id>          re-run the bug's cases: fixed / not fixed",
    f"  Staging: {base}",
    f"  Test roles configured: {', '.join(ready) or 'none'}"
    + (f" | missing: {', '.join(missing)} (/plugin -> Installed -> nt-qa-testing -> Configure options)" if missing else ""),
]
if host != "staging-dashboard.naditarangini.com":
    lines.append(f"  WARNING: staging_base_url host '{host}' is not the staging dashboard; run-web will refuse to start.")

print(json.dumps({
    "systemMessage": "\n".join(lines),
    "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
                           f"nt-qa-testing commands: plan, cases, run-web, report, retest. Staging base URL: {base}. "
                           f"Test roles configured: {', '.join(ready) or 'none'}."},
}))
