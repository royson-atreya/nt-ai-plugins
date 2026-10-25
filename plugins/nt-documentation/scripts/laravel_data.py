#!/usr/bin/env python3
"""Static, read-only map of Laravel models -> tables -> DB connections, and of which files touch which tables.

Never connects to a database and never reads data; it parses PHP source as text.

Usage:
  laravel_data.py <repo> models [--grep text]      model, table, connection, fillable count, relations
  laravel_data.py <repo> uses <path-prefix>         tables touched by files under a prefix
                                                    (via model references in the graph + DB::table literals)
  laravel_data.py <repo> table <table>              models and files that touch one table

<repo>: backend | web | repo directory name. Env: NT_REPOS_DIR.
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph_query import load_graph, repo_path  # noqa: E402

RE_CLASS = re.compile(r"\bclass\s+(\w+)\s+extends\s+([\w\\]+)")
RE_PROP = re.compile(r"protected\s+\$(table|connection)\s*=\s*['\"]([^'\"]+)['\"]")
RE_FILLABLE = re.compile(r"\$fillable\s*=\s*\[(.*?)\]", re.S)
RE_REL = re.compile(r"->(hasMany|hasOne|belongsTo|belongsToMany|morphMany|morphTo|hasManyThrough)\(\s*([\w\\]+)::class")
RE_DBTABLE = re.compile(r"DB::(?:connection\(\s*['\"](\w+)['\"]\s*\)->)?table\(\s*['\"](\w+)['\"]")
RE_SCHEMA = re.compile(r"Schema::(?:connection\(\s*['\"](\w+)['\"]\s*\)->)?(create|table)\(\s*['\"](\w+)['\"]")


def snake_plural(name):
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    if re.search(r"[^aeiou]y$", s):
        return s[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh)$", s):
        return s + "es"
    return s + "s"


def read(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def models(repo_dir):
    out = []
    base = os.path.join(repo_dir, "app", "Models")
    for root, _, files in os.walk(base):
        for fn in sorted(files):
            if not fn.endswith(".php"):
                continue
            path = os.path.join(root, fn)
            src = read(path)
            m = RE_CLASS.search(src)
            if not m:
                continue
            props = dict(RE_PROP.findall(src))
            fill = RE_FILLABLE.search(src)
            out.append({
                "model": m.group(1),
                "file": os.path.relpath(path, repo_dir),
                "table": props.get("table") or snake_plural(m.group(1)),
                "table_inferred": "table" not in props,
                "connection": props.get("connection", "mysql (default)"),
                "fillable": len(re.findall(r"['\"](\w+)['\"]", fill.group(1))) if fill else 0,
                "relations": sorted({f"{k}:{v.rsplit(chr(92), 1)[-1]}" for k, v in RE_REL.findall(src)}),
            })
    return out


def migration_tables(repo_dir):
    created = set()
    mdir = os.path.join(repo_dir, "database", "migrations")
    if os.path.isdir(mdir):
        for fn in os.listdir(mdir):
            if fn.endswith(".php"):
                for _, kind, t in RE_SCHEMA.findall(read(os.path.join(mdir, fn))):
                    if kind == "create":
                        created.add(t)
    return created


def uses(repo_dir, prefix, model_list):
    """Tables touched by files under prefix: model references from the graph + DB::table literals."""
    _, nodes, links = load_graph(repo_dir)
    by_file = {m["file"]: m for m in model_list}
    inside = {i for i, n in nodes.items() if (n.get("source_file") or "").startswith(prefix)}
    hits = collections.defaultdict(lambda: {"via": set(), "files": set()})
    for e in links:
        s, t = e["source"], e["target"]
        if s in inside and t in nodes:
            target_file = nodes[t].get("source_file")
            m = by_file.get(target_file)
            if m and target_file != nodes[s].get("source_file"):
                key = (m["table"], m["connection"])
                hits[key]["via"].add(f"model {m['model']}")
                hits[key]["files"].add(nodes[s]["source_file"])
    files = {nodes[i]["source_file"] for i in inside}
    for f in files:
        p = os.path.join(repo_dir, f)
        if f.endswith(".php") and os.path.isfile(p):
            src = read(p)
            for conn, table in RE_DBTABLE.findall(src):
                key = (table, conn or "mysql (default)")
                hits[key]["via"].add("DB::table")
                hits[key]["files"].add(f)
    return hits


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("repo")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("models"); s.add_argument("--grep"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("uses"); s.add_argument("prefix"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("table"); s.add_argument("table")
    a = p.parse_args()
    name, path = repo_path(a.repo)
    ml = models(path)

    if a.cmd == "models":
        created = migration_tables(path)
        rows = [m for m in ml if not a.grep or a.grep.lower() in (m["model"] + m["table"] + m["file"]).lower()]
        if a.json:
            print(json.dumps(rows, indent=1))
            return
        print(f"# {name}: {len(rows)} models ({sum(1 for m in ml if m['connection'] != 'mysql (default)')} on non-default connections); "
              f"{len(created)} tables created by migrations")
        print("model\ttable\tconnection\tfillable\tin_migrations\trelations\tfile")
        for m in rows:
            t = m["table"] + (" (inferred)" if m["table_inferred"] else "")
            print("\t".join([m["model"], t, m["connection"], str(m["fillable"]), "yes" if m["table"] in created else "no",
                             ",".join(m["relations"]), m["file"]]))
    elif a.cmd == "uses":
        hits = uses(path, a.prefix.rstrip("/"), ml)
        if a.json:
            print(json.dumps([{"table": t, "connection": c, "via": sorted(v["via"]), "files": sorted(v["files"])}
                              for (t, c), v in sorted(hits.items())], indent=1))
            return
        print(f"# {name} :: tables touched under {a.prefix} ({len(hits)})")
        for (t, c), v in sorted(hits.items()):
            print(f"- {t} [{c}] via {', '.join(sorted(v['via']))}; {len(v['files'])} file(s): " + ", ".join(sorted(v["files"])[:4]))
    elif a.cmd == "table":
        ms = [m for m in ml if m["table"] == a.table]
        if not ms:
            close = sorted({m["table"] for m in ml if a.table.rstrip("s") in m["table"]})[:8]
            print(f"no model maps to table '{a.table}'" + (f"; similar: {', '.join(close)}" if close else ""))
        for m in ms:
            print(f"model {m['model']} [{m['connection']}] {m['file']}")
        hits = uses(path, "", ml)
        for (t, c), v in hits.items():
            if t == a.table:
                print(f"used via {', '.join(sorted(v['via']))} in {len(v['files'])} file(s):")
                for f in sorted(v["files"]):
                    print(f"  {f}")


if __name__ == "__main__":
    main()
