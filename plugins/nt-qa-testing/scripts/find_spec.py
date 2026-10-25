#!/usr/bin/env python3
"""Find the nt-docs specs that cover a QA item. Reads only $NT_DOCS_DIR (never the repos).

Usage:
  find_spec.py <term> [<term> ...] [--module <web-module-id>] [--docs <dir>]

Prints JSON:
  web_modules  : matching Nadi-Tarangini-Frontend modules (id, name, status, summary, score)
  specs        : functional specs found per module (web/backend module analyses, via api-links)
  impact       : impact reports mentioning the terms
  journeys     : journeys mentioning the terms or modules
  apis         : web API links for the top modules (method, uri, backend module), max 25 per module
  spec_level   : "functional" if an impact report, module analysis or journey exists, else
                 "map-only" (scope can be listed but expected behaviour is not specified) or "none"
"""
import argparse
import glob
import json
import os
import re
import sys

sys.dont_write_bytecode = True

WEB, BACKEND = "Nadi-Tarangini-Frontend", "Ashoka-World-Backend"


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def front(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    fm = m.group(1) if m else ""
    return {k: v.strip() for k, v in re.findall(r"^(generated_at|graph_stale|module_map_status|status):\s*(.+)$", fm, re.M)}


def score(module, terms):
    hay = {
        3: " ".join([module.get("id", ""), module.get("name", "")]).lower(),
        2: " ".join(module.get("route_prefixes", []) + module.get("entry_points", [])).lower(),
        1: " ".join([module.get("summary", ""), module.get("notes", "") or ""]).lower(),
    }
    return sum(w for t in terms for w, h in hay.items() if t in h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("terms", nargs="*")
    ap.add_argument("--module", action="append", default=[])
    ap.add_argument("--docs", default=os.environ.get("NT_DOCS_DIR", os.path.expanduser("~/atreya-ai/nt-docs")))
    a = ap.parse_args()
    docs = os.path.realpath(os.path.expanduser(a.docs))
    terms = [t.lower() for t in a.terms if len(t) >= 3]

    wmap = load(os.path.join(docs, WEB, "module-map.json")) or {}
    modules = wmap.get("modules", [])
    found = []
    for m in modules:
        s = 100 if m.get("id") in a.module else score(m, terms)
        if s:
            found.append({"id": m["id"], "name": m.get("name"), "status": m.get("status"),
                          "summary": m.get("summary"), "depends_on": m.get("depends_on", []), "score": s})
    found.sort(key=lambda x: -x["score"])
    top = found[:5]

    links = (load(os.path.join(docs, "api-links", "api-links.json")) or {}).get("links", [])
    specs, apis = {}, {}
    for m in top:
        mine = [l for l in links if l.get("client") == "web" and l.get("client_module") == m["id"]]
        backend_mods = sorted({(l.get("backend") or {}).get("module") for l in mine} - {None})
        apis[m["id"]] = [{"method": l.get("method"), "uri": l.get("uri"),
                          "backend_module": (l.get("backend") or {}).get("module")} for l in mine[:25]]
        docs_found = []
        for repo, mid in [(WEB, m["id"])] + [(BACKEND, b) for b in backend_mods]:
            p = os.path.join(docs, repo, "modules", f"{mid}.md")
            if os.path.isfile(p):
                docs_found.append({"path": os.path.relpath(p, docs), **front(read(p))})
        specs[m["id"]] = {"analyses": docs_found, "backend_modules": backend_mods, "api_link_count": len(mine)}

    def mentions(path, extra=()):
        t = read(path).lower()
        return sum(t.count(x) for x in list(terms) + list(extra))

    mod_ids = [m["id"] for m in top]
    impact = [{"path": os.path.relpath(p, docs), "hits": h, **front(read(p))}
              for p in sorted(glob.glob(os.path.join(docs, "impact", "*.md")))
              if (h := mentions(p, mod_ids))]
    journeys = [{"path": os.path.relpath(p, docs), "hits": h, **front(read(p))}
                for p in sorted(glob.glob(os.path.join(docs, "journeys", "*.md")))
                if (h := mentions(p, mod_ids))]
    impact.sort(key=lambda x: -x["hits"])
    journeys.sort(key=lambda x: -x["hits"])

    functional = bool(impact or journeys or any(s["analyses"] for s in specs.values()))
    print(json.dumps({
        "docs_dir": docs,
        "web_map_status": wmap.get("status"),
        "terms": terms,
        "web_modules": found[:10],
        "specs": specs,
        "impact": impact[:5],
        "journeys": journeys[:5],
        "apis": apis,
        "spec_level": "functional" if functional else ("map-only" if top else "none"),
    }, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
