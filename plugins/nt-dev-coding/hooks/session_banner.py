#!/usr/bin/env python3
"""SessionStart: list nt-dev-coding commands and the active task, only under ~/atreya-ai."""
import json
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import devgate  # noqa: E402

try:
    data = json.load(sys.stdin)
except ValueError:
    data = {}
cwd = os.path.realpath(data.get("cwd") or os.getcwd())
if not (cwd == devgate.WORKSPACE or cwd.startswith(devgate.WORKSPACE + os.sep)):
    sys.exit(0)

lines = [
    f"nt-dev-coding (one approved task at a time; you do all git actions; output to {devgate.DEV}/<id>)",
    "  /nt-dev-coding:task <requirement>   ticket + change plan, then stops for approval",
    "  /nt-dev-coding:bug <report>         same, from repro steps and suspected root cause",
    "  approve <id> | revoke <id>          type this yourself; only then can the repos be edited",
    "  /nt-dev-coding:implement <id>       surgical edits on your feature branch + php -l / flutter analyze",
    "  /nt-dev-coding:review <id>          diff.md (+/- per file) and independent review.md",
    "  /nt-dev-coding:handoff <id>         summary, commit message, nt-qa-testing retest plan",
]

summary = "none"
try:
    tid = devgate.active_id()
    if tid:
        rec = devgate.approval(tid)
        title = ""
        try:
            with open(os.path.join(devgate.DEV, tid, "ticket.md"), encoding="utf-8") as f:
                m = re.search(r"^title:\s*(.+)$|^#\s+(.+)$", f.read(), re.M)
                title = (m.group(1) or m.group(2)).strip().strip("'\"") if m else ""
        except OSError:
            pass
        state = "approved" if rec else "NOT approved"
        if rec and rec.get("plan_sha256") != devgate.plan_sha(tid):
            state = "plan changed since approval: re-approve"
        repos = []
        for r in (rec or {}).get("repos", []):
            br = devgate.branch(os.path.join(devgate.REPOS, r))
            prot = br is None or br in devgate.PROTECTED
            repos.append(f"{r} @ {br or 'detached'}" + (" (protected: create a branch)" if prot else ""))
        summary = f"{tid}" + (f" ({title})" if title else "") + f", {state}"
        lines.append(f"  Active task: {summary}")
        lines += [f"    - {r}" for r in repos]
    else:
        lines.append("  Active task: none (plan one with /nt-dev-coding:task, then type `approve <id>`)")
except Exception as e:  # never break session start
    lines.append(f"  Active task: unknown ({e})")

print(json.dumps({
    "systemMessage": "\n".join(lines),
    "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
                           f"nt-dev-coding commands: task, bug, implement, review, handoff. Active task: {summary}."},
}))
