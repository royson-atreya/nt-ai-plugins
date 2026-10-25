#!/usr/bin/env python3
"""Task helper for nt-dev-coding. Reads nt-docs and the repos (read-only git only); writes only base.json.

Usage:
  devtask.py id <text...>              task id: a ticket id on the first line (ZS-1234, NT-BUG-142; not HTTP-500,
                                       UTF-8, ...) or <YYYYMMDD>-<slug of the first line>; id_source says which
  devtask.py specs <term>... [--module <repo-alias>:<module-id>]
                                       nt-docs specs covering the terms; spec_level gates task/bug planning
  devtask.py status <id>               files, plan repos/files (missing ones flagged), approval, active task,
                                       branch per repo, blockers
  devtask.py start <id> [--reset]      implement preflight: fails unless ready; records each repo's base commit
                                       and pre-existing changes in dev/<id>/base.json (kept if it exists)

All output is JSON on stdout. Exit 0 = ok/ready, 1 = blocked or not found, 2 = usage error.
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
import devgate  # noqa: E402

DOCS, DEV, REPOS = devgate.DOCS, devgate.DEV, devgate.REPOS
ALIASES = {"backend": "Ashoka-World-Backend", "web": "Nadi-Tarangini-Frontend", "app": "Nadi-Tarangini-App"}
TICKET_RE = re.compile(r"\b([A-Z]{2,}[A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+)\b")
NOT_TICKETS = {"HTTP", "HTTPS", "UTF", "ISO", "SHA", "MD", "COVID", "TLS", "SSL", "RFC", "IPV", "TCP", "UDP", "API",
               "ERR", "ERROR", "PHP", "JDK", "SDK", "AES", "RSA", "OAUTH", "CVE"}
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are", "be", "when", "it",
        "this", "that", "should", "must", "not", "from", "by", "at", "as", "add", "fix", "bug", "please"}
TASK_FILES = ("bug.md", "ticket.md", "plan.md", "APPROVED", "base.json", "implement.md", "diff.md", "review.md",
              "handoff.md")


def out(obj, code=0):
    print(json.dumps(obj, indent=1, ensure_ascii=False))
    sys.exit(code)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def front(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    fm = m.group(1) if m else ""
    return {k: v.strip().strip("'\"") for k, v in
            re.findall(r"^(generated_at|graph_stale|module_map_status|status|title|kind|module):\s*(.+)$", fm, re.M)}


def front_list(text, key):
    """A list-valued front-matter key (inline [a, b] or block '- a')."""
    return devgate.plan_repos(text, key)


def git(root, *args):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=60)
    return r.stdout if r.returncode == 0 else None


def dirty(root):
    """Paths with uncommitted changes (tracked or untracked), secrets included by name only."""
    s = git(root, "status", "--porcelain=v1", "--untracked-files=all") or ""
    return sorted({line[3:].split(" -> ")[-1].strip('"') for line in s.splitlines() if len(line) > 3})


# ---------- id ----------

def cmd_id(text):
    first = next((l for l in text.splitlines() if l.strip()), "")
    m = next((m for m in TICKET_RE.finditer(first) if m.group(1).split("-")[0] not in NOT_TICKETS), None)
    source = "ticket-in-text" if m else "slug"
    if m:
        tid = m.group(1)
    else:
        words = [w for w in re.findall(r"[a-z0-9]+", first.lower()) if w not in STOP][:6]
        tid = datetime.date.today().strftime("%Y%m%d") + "-" + ("-".join(words) or "task")
    tid = tid[:80]
    d = os.path.join(DEV, tid)
    out({"id": tid, "id_source": source, "dir": d, "exists": os.path.isdir(d),
         "existing_files": sorted(f for f in TASK_FILES if os.path.exists(os.path.join(d, f)))})


# ---------- specs ----------

def score(module, terms):
    hay = {
        3: " ".join([module.get("id", ""), module.get("name", "")]).lower(),
        2: " ".join(module.get("route_prefixes", []) + module.get("entry_points", [])).lower(),
        1: " ".join([module.get("summary", ""), module.get("notes", "") or ""]).lower(),
    }
    return sum(w for t in terms for w, h in hay.items() if t in h)


def cmd_specs(terms, wanted):
    if not os.path.isdir(DOCS):
        out({"error": f"nt-docs not found at {DOCS}; set NT_DOCS_DIR or run /nt-documentation:map first"}, 1)
    terms = [t.lower() for t in terms if len(t) >= 3]
    wanted = {(ALIASES.get(w.split(":")[0], w.split(":")[0]), w.split(":", 1)[1]) for w in wanted if ":" in w}
    modules = []
    for alias, repo in ALIASES.items():
        mm = load(os.path.join(DOCS, repo, "module-map.json")) or {}
        for m in mm.get("modules", []):
            s = 100 if (repo, m.get("id")) in wanted else score(m, terms)
            if not s:
                continue
            p = os.path.join(DOCS, repo, "modules", f"{m['id']}.md")
            modules.append({"ref": f"{alias}:{m['id']}", "repo": repo, "name": m.get("name"), "score": s,
                            "map_status": mm.get("status"), "summary": m.get("summary"),
                            "analysis": (os.path.relpath(p, DOCS) if os.path.isfile(p) else None),
                            **({"analysis_stamp": front(read(p))} if os.path.isfile(p) else {})})
    modules.sort(key=lambda x: -x["score"])
    top = modules[:8]
    ids = [m["ref"].split(":", 1)[1] for m in top]

    def hits(path):
        t = read(path).lower()
        return sum(t.count(x) for x in terms + ids)

    impact = sorted(({"path": os.path.relpath(p, DOCS), "hits": h, **front(read(p))}
                     for p in glob.glob(os.path.join(DOCS, "impact", "*.md")) if (h := hits(p))),
                    key=lambda x: -x["hits"])[:5]
    journeys = sorted(({"path": os.path.relpath(p, DOCS), "hits": h}
                       for p in glob.glob(os.path.join(DOCS, "journeys", "*.md")) if (h := hits(p))),
                      key=lambda x: -x["hits"])[:5]
    links = (load(os.path.join(DOCS, "api-links", "api-links.json")) or {}).get("links", [])
    api_counts = {}
    for m in top:
        alias, mid = m["ref"].split(":", 1)
        api_counts[m["ref"]] = sum(1 for l in links if (alias in ("web", "app") and l.get("client") == alias and
                                                        l.get("client_module") == mid) or
                                   (alias == "backend" and (l.get("backend") or {}).get("module") == mid))
    analyses = [m for m in top if m["analysis"]]
    level = "impact" if impact else "analysis" if analyses else "map-only" if top else "none"
    out({"docs_dir": DOCS, "terms": terms, "modules": top, "impact": impact, "journeys": journeys,
         "api_links_present": bool(links), "api_link_counts": api_counts, "spec_level": level,
         "gate": "pass" if level in ("impact", "analysis") else "stop",
         "hint": None if level in ("impact", "analysis") else
         'no impact report or module analysis covers this; suggest /nt-documentation:impact "<change>" '
         "(or /nt-documentation:analyze <repo> <module>) first"})


# ---------- status / start ----------

def task_status(tid):
    d = os.path.join(DEV, tid)
    if not devgate.ID_RE.match(tid) or not os.path.isdir(d):
        out({"id": tid, "error": f"no task folder {d}"}, 1)
    plan = read(os.path.join(d, "plan.md"))
    rec = devgate.approval(tid)
    current = bool(rec) and rec.get("plan_sha256") == devgate.plan_sha(tid)
    repos = devgate.plan_repos(plan) or (rec or {}).get("repos") or []
    info, blockers = [], []
    if not plan:
        blockers.append("no plan.md: run /nt-dev-coding:task or /nt-dev-coding:bug")
    if not rec:
        blockers.append(f"not approved: the user types `approve {tid}`")
    elif not current:
        blockers.append(f"plan.md changed after approval: the user re-approves with `approve {tid}`")
    if devgate.active_id() != tid:
        blockers.append(f"not the active task (active: {devgate.active_id() or 'none'}); `approve {tid}` makes it active")
    for r in repos:
        root = os.path.join(REPOS, r)
        if not os.path.isdir(root):
            info.append({"repo": r, "error": "not found"})
            blockers.append(f"repo {r} not found under {REPOS}")
            continue
        br = devgate.branch(root)
        prot = br is None or br in devgate.PROTECTED
        if prot:
            blockers.append(devgate.protected_hint(r, root, br, tid))
        info.append({"repo": r, "root": root, "branch": br, "protected": prot,
                     "head": (git(root, "rev-parse", "HEAD") or "").strip() or None, "dirty": dirty(root)})
    return {"id": tid, "dir": d,
            "files": sorted(f for f in TASK_FILES if os.path.exists(os.path.join(d, f))),
            "kind": front(plan).get("kind") or ("bug" if os.path.exists(os.path.join(d, "bug.md")) else "task"),
            "plan_repos": devgate.plan_repos(plan), "plan_files": front_list(plan, "files"),
            "missing_files": [f for f in front_list(plan, "files") if not f.endswith("/") and
                              not os.path.exists(os.path.join(REPOS, f))],
            "files_outside_repos": [f for f in front_list(plan, "files") if f.split("/", 1)[0] not in
                                    devgate.plan_repos(plan)],
            "approved": bool(rec), "approval_current": current, "approved_at": (rec or {}).get("approved_at"),
            "active": devgate.active_id() == tid, "repos": info, "ready": not blockers, "blockers": blockers}


def cmd_start(tid, reset):
    st = task_status(tid)
    if not st["ready"]:
        out(st, 1)
    path = os.path.join(st["dir"], "base.json")
    base = load(path)
    if base is None or reset:
        base = {"id": tid, "recorded_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "repos": {r["repo"]: {"commit": r["head"], "branch": r["branch"], "dirty_before": r["dirty"]}
                          for r in st["repos"]}}
        with open(path, "w") as f:
            json.dump(base, f, indent=1)
            f.write("\n")
        st["base"] = "recorded"
    else:
        added = [r for r in st["repos"] if r["repo"] not in base.get("repos", {})]
        for r in added:  # a re-plan added a repo: record its base now
            base.setdefault("repos", {})[r["repo"]] = {"commit": r["head"], "branch": r["branch"],
                                                       "dirty_before": r["dirty"]}
        if added:
            with open(path, "w") as f:
                json.dump(base, f, indent=1)
                f.write("\n")
        st["base"] = "kept" + (f", added {', '.join(r['repo'] for r in added)}" if added else "") + \
                     " (--reset records again; only before any edit)"
    st["base_json"] = base
    st["warnings"] = [f"{r}: {len(v['dirty_before'])} file(s) were already uncommitted before implement; "
                      "they will show as pre-existing in diff.md" for r, v in base["repos"].items() if v["dirty_before"]]
    out(st)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("id").add_argument("text", nargs="+")
    sp = sub.add_parser("specs")
    sp.add_argument("terms", nargs="*")
    sp.add_argument("--module", action="append", default=[])
    sub.add_parser("status").add_argument("id")
    st = sub.add_parser("start")
    st.add_argument("id")
    st.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.cmd == "id":
        cmd_id(" ".join(a.text))
    elif a.cmd == "specs":
        cmd_specs(a.terms, a.module)
    elif a.cmd == "status":
        st = task_status(a.id)
        out(st, 0 if st["ready"] else 1)
    elif a.cmd == "start":
        cmd_start(a.id, a.reset)


if __name__ == "__main__":
    main()
