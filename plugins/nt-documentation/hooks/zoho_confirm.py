#!/usr/bin/env python3
"""PreToolUse: ask the user before any Zoho tool call that is not a read."""
import json
import re
import sys

READ_ONLY = re.compile(r"__(ZohoSprints_)?(Get|List|Search)[A-Za-z]*$")

try:
    tool = json.load(sys.stdin).get("tool_name", "")
except Exception:  # fail safe: ask rather than silently allow
    tool = "unknown Zoho tool"
if READ_ONLY.search(tool):
    sys.exit(0)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": f"nt-documentation: '{tool.split('__')[-1]}' writes to Zoho Sprints. Confirm before it runs.",
    }
}))
