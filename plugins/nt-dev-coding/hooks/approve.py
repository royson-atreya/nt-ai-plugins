#!/usr/bin/env python3
"""UserPromptSubmit: record the user's approval of a planned nt-dev-coding task.

Only a prompt that is exactly `approve <id>` or `revoke <id>` (case-insensitive, optional trailing '.')
acts. Claude cannot create these markers itself (guard.py blocks it), so APPROVED always means the
user typed the approval.

approve <id>: needs $NT_DOCS_DIR/dev/<id>/plan.md with a `repos:` front-matter list of repo folders
              under $NT_REPOS_DIR. Writes dev/<id>/APPROVED (JSON: id, repos, plan_sha256, approved_at)
              and makes <id> the active task (dev/ACTIVE).
revoke <id>:  removes dev/<id>/APPROVED, and dev/ACTIVE if it names <id>.
"""
import datetime
import json
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import devgate  # noqa: E402

CMD = re.compile(r"^\s*(approve|revoke)\s+(\S+?)\s*\.?\s*$", re.I)


def say(user_msg, context):
    print(json.dumps({"systemMessage": user_msg, "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": context}}))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        sys.exit(0)
    m = CMD.match(str(data.get("prompt") or ""))
    if not m:
        sys.exit(0)
    cwd = data.get("cwd")
    if cwd and not devgate._under(os.path.realpath(cwd), devgate.WORKSPACE):
        sys.exit(0)  # only sessions in the Nadi Tarangini workspace
    verb, tid = m.group(1).lower(), m.group(2)
    task_dir = os.path.join(devgate.DEV, tid)
    if not devgate.ID_RE.match(tid) or not os.path.isdir(task_dir):
        if os.path.isdir(devgate.DEV):
            say(f"nt-dev-coding: no task '{tid}' in {devgate.DEV}; nothing {verb}d.",
                f"The user typed `{verb} {tid}` but nt-dev-coding has no such task folder; nothing was recorded. "
                "List the folders in nt-docs/dev and ask which id they meant.")
        sys.exit(0)  # not an nt-dev-coding prompt at all
    approved = os.path.join(task_dir, "APPROVED")
    active = os.path.join(devgate.DEV, "ACTIVE")

    if verb == "revoke":
        for f in (approved,) + ((active,) if devgate.active_id() == tid else ()):
            if os.path.exists(f):
                os.remove(f)
        say(f"nt-dev-coding: approval of {tid} revoked; repo edits for it are blocked again.",
            f"The user revoked approval of nt-dev-coding task {tid}. Do not edit the repos for it.")

    plan = os.path.join(task_dir, "plan.md")
    try:
        with open(plan, encoding="utf-8") as f:
            repos = devgate.plan_repos(f.read())
    except OSError:
        say(f"nt-dev-coding: NOT approved: {plan} does not exist.",
            f"The user typed `approve {tid}` but there is no plan.md; approval was NOT recorded. "
            f"Run /nt-dev-coding:task or /nt-dev-coding:bug first.")
    bad = [r for r in repos if not os.path.isdir(os.path.join(devgate.REPOS, r, ".git"))
           and not os.path.isfile(os.path.join(devgate.REPOS, r, ".git"))]
    if not repos or bad:
        why = "its front-matter has no `repos:` list" if not repos else f"unknown repos {', '.join(bad)}"
        say(f"nt-dev-coding: NOT approved: plan.md of {tid}: {why}.",
            f"Approval of {tid} was NOT recorded because plan.md {why}. Fix the front-matter `repos:` list "
            f"(full folder names under {devgate.REPOS}) and ask the user to type `approve {tid}` again.")

    rec = {"id": tid, "repos": repos, "plan_sha256": devgate.plan_sha(tid),
           "approved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "approved_by": "user prompt (nt-dev-coding approve hook)"}
    with open(approved, "w") as f:
        json.dump(rec, f, indent=2)
        f.write("\n")
    with open(active, "w") as f:
        f.write(tid + "\n")

    lines, blocked = [], []
    for r in repos:
        root = os.path.join(devgate.REPOS, r)
        br = devgate.branch(root)
        if br is None or br in devgate.PROTECTED:
            blocked.append(devgate.protected_hint(r, root, br, tid))
        lines.append(f"{r}: {br or 'detached HEAD'}" + (" (protected)" if br is None or br in devgate.PROTECTED else ""))
    msg = f"nt-dev-coding: {tid} approved and active. Repos: " + "; ".join(lines)
    ctx = (f"The user approved nt-dev-coding task {tid} (recorded by hook; repos: {', '.join(repos)}). "
           f"Reply only by telling the user the next step is `/nt-dev-coding:implement {tid}`; do not edit the repos "
           "in this turn or anywhere outside the implement skill (its preflight records the base commit).")
    if blocked:
        ctx += " Edits stay blocked until the user switches branch: " + " ".join(blocked)
    say(msg, ctx)


if __name__ == "__main__":
    main()
