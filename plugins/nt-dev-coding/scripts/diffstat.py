#!/usr/bin/env python3
"""Build dev/<id>/diff.md: every added/removed line of a task's change, grouped by file, with +/- counts.

Usage:
  diffstat.py <id> [--json | --stdout]

Compares each approved repo's working tree with the base commit recorded in dev/<id>/base.json
(by `devtask.py start`; falls back to HEAD), so commits the user made after implement still count.
Untracked new files are shown as all-added. Read-only git only.

Per file it records status (A/M/D/R), +/- counts, and flags:
  unplanned     changed but not listed in plan.md `files:` (or under a listed folder ending in /)
  pre-existing  unplanned and already uncommitted before implement started (not the task's change)
  mixed         planned, but already uncommitted before implement: task change + earlier edits in one file
  secret        secret file name: content never shown
  binary        no line diff
  redacted      a line looked like a credential and was masked (review should treat it as a finding)
Planned files with no change are listed too.

diff_sha256 is a hash of the change itself (files, statuses, counts, every hunk line), independent of
time: review records it in review.md as reviewed_diff_sha256 and handoff compares it to detect code
that changed after review.

Writes diff.md and prints a JSON summary. --json prints the summary only (writes nothing);
--stdout prints diff.md instead of writing it.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))
import devgate  # noqa: E402

SECRET_NAMES = re.compile(r"(^|/)(\.env(\..*)?|[^/]*\.jks|[^/]*\.keystore|firebase-[^/]*\.json|google-services\.json|"
                          r"GoogleService-Info\.plist)$")
SECRET_CONTENT = re.compile(
    r"AIza[0-9A-Za-z_\-]{35}|rzp_(?:live|test)_[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\"private_key\"\s*:|(?:sk|pk)_live_[A-Za-z0-9]{10,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|Bearer\s+[A-Za-z0-9\-_.=]{24,}"
    r"|(?:password|passwd|secret|api_key|auth_key)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]", re.I)
MAX_LINES = 4000  # per file; beyond this the diff is cut with a note


def git(root, *args):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, errors="replace", timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} failed in {root}: {r.stderr.strip()[:200]}")
    return r.stdout


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def planned(rel_repo_path, plan_files):
    for p in plan_files:
        p = p.strip()
        p = p[2:] if p.startswith("./") else p
        if p == rel_repo_path or (p.endswith("/") and rel_repo_path.startswith(p)):
            return True
    return False


def redact(lines):
    hit = False
    out = []
    for line in lines:
        if line[:1] in "+-" and not line.startswith(("+++", "---")) and SECRET_CONTENT.search(line):
            out.append(line[0] + "    [redacted by diffstat: line looks like a credential]")
            hit = True
        else:
            out.append(line)
    return out, hit


def repo_changes(name, root, base):
    """[(status, path, old_path)] changed vs base in the working tree, plus untracked files."""
    changes = []
    raw = git(root, "diff", "--name-status", "-z", "-M", base, "--")
    parts = [p for p in raw.split("\0") if p != ""]
    i = 0
    while i < len(parts):
        st = parts[i]
        if st.startswith(("R", "C")):
            changes.append((st[0], parts[i + 2], parts[i + 1]))
            i += 3
        else:
            changes.append((st[0], parts[i + 1], None))
            i += 2
    for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if p:
            changes.append(("A", p, None))
    return changes


def file_diff(root, base, status, path, untracked):
    """(plus, minus, lines, binary)"""
    if untracked:
        full = os.path.join(root, path)
        try:
            with open(full, encoding="utf-8") as f:
                body = f.read().splitlines()
        except (UnicodeDecodeError, OSError):
            return 0, 0, [], True
        return len(body), 0, [f"@@ -0,0 +1,{len(body)} @@ (new untracked file)"] + ["+" + l for l in body], False
    num = git(root, "diff", "--numstat", "-M", base, "--", path).split("\t")
    if len(num) >= 2 and num[0] == "-":
        return 0, 0, [], True
    plus, minus = (int(num[0]), int(num[1])) if len(num) >= 2 and num[0].isdigit() else (0, 0)
    patch = git(root, "diff", "-U3", "--no-color", "--no-ext-diff", "-M", base, "--", path).splitlines()
    start = next((k for k, l in enumerate(patch) if l.startswith("@@")), len(patch))
    return plus, minus, patch[start:], False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--stdout", action="store_true", help="print diff.md instead of writing it")
    mode.add_argument("--json", action="store_true", help="print the JSON summary only; write nothing")
    a = ap.parse_args()
    tid = a.id
    d = os.path.join(devgate.DEV, tid)
    if not devgate.ID_RE.match(tid) or not os.path.isdir(d):
        print(json.dumps({"error": f"no task folder {d}"}))
        sys.exit(1)
    try:
        with open(os.path.join(d, "plan.md"), encoding="utf-8") as f:
            plan = f.read()
    except OSError:
        plan = ""
    rec = devgate.approval(tid) or {}
    base_json = load(os.path.join(d, "base.json")) or {}
    repos = rec.get("repos") or devgate.plan_repos(plan)
    plan_files = devgate.plan_repos(plan, "files")

    files, repo_meta, errors = [], [], []
    for name in repos:
        root = os.path.join(devgate.REPOS, name)
        b = (base_json.get("repos") or {}).get(name) or {}
        base = b.get("commit") or "HEAD"
        pre = set(b.get("dirty_before") or [])
        try:
            untracked = set(p for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if p)
            changes = repo_changes(name, root, base)
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            errors.append(str(e))
            continue
        try:
            head = git(root, "rev-parse", "HEAD").strip()
        except RuntimeError as e:
            errors.append(str(e))
            continue
        repo_meta.append({"repo": name, "base": base, "branch": devgate.branch(root), "head": head})
        repo_plan = [p.split("/", 1)[1] for p in plan_files if p.startswith(name + "/")]
        for status, path, old in changes:
            rec_f = {"repo": name, "path": path, "old_path": old, "status": status, "plus": 0, "minus": 0,
                     "flags": [], "lines": []}
            is_planned = planned(path, repo_plan)
            if not is_planned:
                rec_f["flags"].append("unplanned")
            if path in pre:
                # planned + already dirty: the task's change is mixed with earlier uncommitted edits
                rec_f["flags"].append("mixed" if is_planned else "pre-existing")
            if SECRET_NAMES.search(path):
                rec_f["flags"].append("secret")
            else:
                plus, minus, lines, binary = file_diff(root, base, status, path, path in untracked)
                rec_f["plus"], rec_f["minus"] = plus, minus
                if binary:
                    rec_f["flags"].append("binary")
                lines, hit = redact(lines)
                if hit:
                    rec_f["flags"].append("redacted")
                if len(lines) > MAX_LINES:
                    lines = lines[:MAX_LINES] + [f"... cut: {len(lines) - MAX_LINES} more diff lines (see git diff)"]
                rec_f["lines"] = lines
            files.append(rec_f)
        changed = {f["path"] for f in files if f["repo"] == name}
        for p in repo_plan:
            if not p.endswith("/") and p not in changed:
                files.append({"repo": name, "path": p, "old_path": None, "status": "-", "plus": 0, "minus": 0,
                              "flags": ["planned-unchanged"], "lines": []})

    h = hashlib.sha256()
    for f in sorted(files, key=lambda x: (x["repo"], x["path"])):
        h.update(json.dumps([f["repo"], f["path"], f["old_path"], f["status"], f["plus"], f["minus"],
                             sorted(f["flags"]), f["lines"]], ensure_ascii=False).encode())
    diff_sha = h.hexdigest()
    plus = sum(f["plus"] for f in files)
    minus = sum(f["minus"] for f in files)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    km = re.search(r"(?m)^kind:\s*(\w+)", plan)
    md = ["---", "generated_by: nt-dev-coding/review (diffstat.py)", f"generated_at: {now}", f"task_id: {tid}",
          f"kind: {km.group(1) if km else 'task'}", "repos:"]
    for r in repo_meta:
        md += [f"  - repo: {r['repo']}", f"    branch: {r['branch'] or 'detached'}", f"    base: {r['base']}",
               f"    head: {r['head']}"]
    md += [f"diff_sha256: {diff_sha}", f"totals: {{files: {sum(1 for f in files if f['status'] != '-')}, plus: {plus}, minus: {minus}}}", "---", "",
           f"# Diff for {tid}", "",
           f"Working tree compared with the base commit recorded when implement started"
           f"{'' if base_json else ' (no base.json: compared with HEAD)'}. New files in git-ignored paths are not listed. "
           f"**{plus} added, {minus} removed** lines in {sum(1 for f in files if f['status'] != '-')} file(s).", ""]
    if errors:
        md += ["> Errors: " + "; ".join(errors), ""]
    md += ["| # | File | Status | + | − | Flags |", "|---|---|---|---|---|---|"]
    for n, f in enumerate(files, 1):
        name = f"{f['repo']}/{f['path']}" + (f" (from {f['old_path']})" if f["old_path"] else "")
        md.append(f"| {n} | `{name}` | {f['status']} | {f['plus']} | {f['minus']} | {', '.join(f['flags'])} |")
    for n, f in enumerate(files, 1):
        if f["status"] == "-":
            continue
        md += ["", f"## {n}. {f['repo']}/{f['path']}  (+{f['plus']} −{f['minus']}, {f['status']})", ""]
        if "secret" in f["flags"]:
            md.append("_Secret file: content not shown. A task must never change it; treat as a review finding._")
        elif "binary" in f["flags"]:
            md.append("_Binary file: no line diff._")
        elif f["lines"]:
            md += ["````diff"] + f["lines"] + ["````"]
        else:
            md.append("_No line changes (mode or rename only)._")
    text = "\n".join(md) + "\n"
    if a.stdout:
        print(text)
        return
    if not a.json:
        with open(os.path.join(d, "diff.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
    print(json.dumps({"id": tid, "diff_md": None if a.json else os.path.join(d, "diff.md"), "diff_sha256": diff_sha,
                      "files_changed": sum(1 for f in files if f["status"] != "-"), "plus": plus, "minus": minus,
                      "files": [{k: v for k, v in f.items() if k != "lines"} for f in files],
                      "unplanned": [f"{f['repo']}/{f['path']}" for f in files if "unplanned" in f["flags"]],
                      "pre_existing": [f"{f['repo']}/{f['path']}" for f in files if "pre-existing" in f["flags"]],
                      "mixed": [f"{f['repo']}/{f['path']}" for f in files if "mixed" in f["flags"]],
                      "flags_needing_review": sorted({fl for f in files for fl in f["flags"]} & {"secret", "redacted"}),
                      "errors": errors}, indent=1))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
