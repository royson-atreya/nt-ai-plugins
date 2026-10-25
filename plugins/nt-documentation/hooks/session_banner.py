#!/usr/bin/env python3
"""SessionStart: list nt-documentation commands and graph freshness, only under ~/atreya-ai."""
import json
import os
import sys

sys.dont_write_bytecode = True  # never write .pyc into the plugin cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

WORKSPACE = os.path.realpath(os.path.expanduser("~/atreya-ai"))

try:
    data = json.load(sys.stdin)
except ValueError:
    data = {}
cwd = os.path.realpath(data.get("cwd") or os.getcwd())
if not (cwd == WORKSPACE or cwd.startswith(WORKSPACE + os.sep)):
    sys.exit(0)

lines = [
    "nt-documentation (read-only; output to ~/atreya-ai/nt-docs)",
    "  /nt-documentation:map <backend|web|app>     module map from graphify",
    "  /nt-documentation:analyze <repo> <module>   explain one module + functional spec",
    "  /nt-documentation:link-apis                 screen -> API -> route -> controller -> table",
    "  /nt-documentation:diagram <module|system>   draw.io diagrams (auto-checked)",
    "  /nt-documentation:impact <change request>   affected modules/screens/APIs/tables + estimate",
    "  /nt-documentation:plan-sprint <impact file> Zoho Sprints P7 tasks (after your approval)",
]

stale = []
try:
    from graph_query import stamp

    for repo in ("backend", "web", "app"):
        try:
            s = stamp(repo)
        except SystemExit:
            stale.append(f"{repo}: repo or graph missing")
            continue
        if s["graph_stale"]:
            stale.append(f"{s['repo']}: graph {str(s['graph_commit'])[:9]} != HEAD {str(s['commit'])[:9]} (run `graphify update .`)")
except Exception as e:  # never break session start
    stale.append(f"freshness check failed: {e}")

if stale:
    lines.append("  Graph freshness warnings:")
    lines += [f"    - {s}" for s in stale]

banner = "\n".join(lines)
print(json.dumps({
    "systemMessage": banner,
    "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
                           "nt-documentation commands: map, analyze, link-apis, diagram, impact, plan-sprint."
                           + (" Stale graphs: " + "; ".join(stale) if stale else "")},
}))
