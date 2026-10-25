#!/usr/bin/env python3
"""Deterministic starting point for change-impact analysis.

Given search terms taken from a change request (feature words, URIs, table names, screen or
controller names), find matching modules, APIs, screens and tables across the three NT repos,
then expand the knock-on effects backwards: who reads or writes the matched tables, which screens
call the matched APIs, and which modules depend on the matched files (graph callers).

Usage:
  impact_seed.py <term> [<term> ...] [--json] [--limit N]

Inputs: $NT_DOCS_DIR/api-links/api-links.json and <repo>/module-map.json (if present), and each
repo's graphify graph. Read-only.
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph_query import load_graph, repo_path  # noqa: E402

REPOS = {"backend": "Ashoka-World-Backend", "web": "Nadi-Tarangini-Frontend", "app": "Nadi-Tarangini-App"}
STRUCTURAL = {"contains", "method", "defines"}


def docs_dir():
    return os.path.expanduser(os.environ.get("NT_DOCS_DIR", "~/atreya-ai/nt-docs"))


def load(path):
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("terms", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=25)
    a = ap.parse_args()
    terms = [t.lower() for t in a.terms]

    def hit(text):
        t = (text or "").lower()
        return [x for x in terms if x in t]

    links_doc = load(os.path.join(docs_dir(), "api-links", "api-links.json"))
    maps = {k: load(os.path.join(docs_dir(), v, "module-map.json")) for k, v in REPOS.items()}
    missing_inputs = [n for n, v in [("api-links.json", links_doc)] + [(f"{k} module-map.json", m) for k, m in maps.items()] if not v]
    from module_map import owner

    def own(repo, path):
        m = maps.get(repo)
        return owner(m["modules"], path)[0] if m and path else None

    result = {"terms": a.terms, "missing_inputs": missing_inputs, "modules": collections.defaultdict(lambda: {"reasons": set(), "score": 0}),
              "apis": {}, "tables": {}, "screens": {}, "graph_files": collections.defaultdict(list), "callers": {}}

    def bump(repo, mid, reason, w=1):
        if not mid:
            return
        e = result["modules"][(repo, mid)]
        e["reasons"].add(reason)
        e["score"] += w

    # 1. module map names / summaries
    for repo, m in maps.items():
        for mod in (m or {}).get("modules", []):
            h = hit(" ".join([mod["id"], mod["name"], mod.get("summary", ""), mod["product_area"], " ".join(mod.get("entry_points", []))]))
            if h:
                bump(repo, mod["id"], f"module map mentions {', '.join(h)}", 3)

    # 2. api-links: uris, controllers, screens, tables
    links = (links_doc or {}).get("links", [])
    for l in links:
        b = l["backend"]
        fields = {"uri": l["uri"], "controller": f"{b['controller']}@{b['action']}", "screens": " ".join(l["screens"]),
                  "client": l["client_entry"]["file"], "tables": " ".join(t["table"] for t in l["tables"] if t["level"] != "file")}
        h = {k: hit(v) for k, v in fields.items()}
        if not any(h.values()):
            continue
        key = f"{','.join(b['methods'])} {b['uri']}"
        api = result["apis"].setdefault(key, {"controller": fields["controller"], "route": b["route"], "backend_module": b["module"],
                                              "clients": set(), "screens": set(), "tables": set(), "why": set()})
        api["clients"].add(l["client"])
        api["screens"].update(l["screens"][:5])
        api["tables"].update(f"{t['table']}{'(W)' if t['write'] else ''}" for t in l["tables"] if t["level"] != "file")
        api["why"].update(f"{k}:{x}" for k, v in h.items() for x in v)
        bump("backend", b["module"], "api-links match", 2)
        bump(l["client"], l["client_module"], "api-links match", 2)
        for s in l["screens"]:
            if hit(s):
                result["screens"].setdefault(s, set()).add(key)

    # 3. tables by name -> reverse: every API reading or writing them
    for l in links:
        for t in l["tables"]:
            if t["level"] == "file" or not hit(t["table"]):
                continue
            tb = result["tables"].setdefault(t["table"], {"connection": t["connection"], "writers": set(), "readers": set(), "screens": set()})
            key = f"{','.join(l['backend']['methods'])} {l['backend']['uri']}"
            (tb["writers"] if t["write"] else tb["readers"]).add(key)
            tb["screens"].update(l["screens"][:3])
            bump("backend", l["backend"]["module"], f"touches table {t['table']}", 2)
            bump(l["client"], l["client_module"], f"screen uses table {t['table']}", 1)

    # 4. graph search per repo + callers (knock-on effects)
    for repo, rname in REPOS.items():
        try:
            _, path = repo_path(repo)
            _, nodes, edges = load_graph(path)
        except SystemExit:
            continue
        files = set()
        for n in nodes.values():
            sf = n.get("source_file") or ""
            if "/" in sf and (hit(n["label"]) or hit(sf)):
                files.add(sf)
        result["graph_files"][repo] = sorted(files)[: a.limit * 4]
        for f in files:
            bump(repo, own(repo, f), "graph label/file match", 1)
        ids = {i for i, n in nodes.items() if n.get("source_file") in files}
        callers = collections.Counter()
        for e in edges:
            if e.get("relation") in STRUCTURAL:
                continue
            if e["target"] in ids and e["source"] in nodes:
                src = nodes[e["source"]].get("source_file") or ""
                if "/" in src and src not in files:
                    callers[own(repo, src) or os.path.dirname(src)] += 1
        result["callers"][repo] = callers.most_common(a.limit)
        for mid, c in callers.items():
            if maps.get(repo) and any(m["id"] == mid for m in maps[repo]["modules"]):
                bump(repo, mid, f"depends on matched code ({c} refs)", 0)

    out = {
        "terms": a.terms,
        "missing_inputs": missing_inputs,
        "modules": sorted([{"repo": r, "module": m, "score": v["score"], "reasons": sorted(v["reasons"])}
                           for (r, m), v in result["modules"].items()], key=lambda x: -x["score"]),
        "apis": [{"api": k, **{kk: sorted(vv) if isinstance(vv, set) else vv for kk, vv in v.items()}}
                 for k, v in sorted(result["apis"].items())][: a.limit * 3],
        "tables": {k: {kk: sorted(vv) if isinstance(vv, set) else vv for kk, vv in v.items()} for k, v in result["tables"].items()},
        "screens": {k: sorted(v) for k, v in result["screens"].items()},
        "graph_files": dict(result["graph_files"]),
        "callers": result["callers"],
    }
    if a.json:
        print(json.dumps(out, indent=1))
        return
    print(f"# impact seed for: {', '.join(a.terms)}")
    if missing_inputs:
        print(f"WARNING missing inputs (lower confidence): {', '.join(missing_inputs)}")
    print("\n## Candidate modules (score, reasons)")
    for m in out["modules"][: a.limit]:
        print(f"{m['score']:4d}  {m['repo']}:{m['module']}  ({'; '.join(m['reasons'][:4])})")
    print(f"\n## Matching APIs ({len(out['apis'])})")
    for x in out["apis"][: a.limit]:
        print(f"- {x['api']}  -> {x['controller'].rsplit(chr(92), 1)[-1]}  [{x['backend_module']}]  clients={','.join(x['clients'])}  "
              f"tables={','.join(x['tables'][:5])}  screens={len(x['screens'])}  why={','.join(x['why'])}")
    print(f"\n## Matching tables ({len(out['tables'])}) with readers/writers")
    for t, v in out["tables"].items():
        print(f"- {t} [{v['connection']}]: {len(v['writers'])} writer API(s), {len(v['readers'])} reader API(s), {len(v['screens'])} screen(s)")
        for w in v["writers"][:6]:
            print(f"    W {w}")
    print("\n## Graph file matches per repo")
    for repo, fs in out["graph_files"].items():
        print(f"- {repo}: {len(fs)} file(s): " + ", ".join(fs[:8]))
    print("\n## Knock-on effects: modules/folders that reference matched code (graph callers)")
    for repo, cs in out["callers"].items():
        if cs:
            print(f"- {repo}: " + ", ".join(f"{m} ({c})" for m, c in cs[:10]))


if __name__ == "__main__":
    main()
