#!/usr/bin/env python3
"""Compact, read-only queries over a repo's graphify graph (graphify-out/graph.json).

graph.json files are 1-10 MB; this script keeps agent context small by returning
summaries instead of raw JSON. Standard library only.

Usage:
  graph_query.py stamp   <repo>                        freshness stamp (JSON)
  graph_query.py summary <repo> [--depth N]            node counts per folder + top communities
  graph_query.py folder  <repo> <path-prefix> [--limit N]
                                                       files under a prefix, their main symbols,
                                                       and dependencies in/out of the prefix
  graph_query.py file    <repo> <path>                 symbols in one file and their edges
  graph_query.py search  <repo> <term> [--limit N]     nodes whose label or file matches term
  graph_query.py neighbors <repo> <label|id> [--relation R] [--limit N]

<repo> is a repo directory name or alias: backend, web, app.
Env: NT_REPOS_DIR (default ~/atreya-ai/repos).
"""
import argparse
import collections
import datetime
import json
import os
import subprocess
import sys

ALIASES = {
    "backend": "Ashoka-World-Backend",
    "web": "Nadi-Tarangini-Frontend",
    "frontend": "Nadi-Tarangini-Frontend",
    "app": "Nadi-Tarangini-App",
    "mobile": "Nadi-Tarangini-App",
}


def repos_dir():
    return os.path.expanduser(os.environ.get("NT_REPOS_DIR", "~/atreya-ai/repos"))


def repo_path(repo):
    name = ALIASES.get(repo.lower(), repo)
    path = os.path.join(repos_dir(), name)
    if not os.path.isdir(path):
        sys.exit(f"error: repo not found: {path}")
    return name, path


def load_graph(path):
    gpath = os.path.join(path, "graphify-out", "graph.json")
    if not os.path.isfile(gpath):
        sys.exit(f"error: no graphify graph at {gpath}; run `graphify .` in the repo first")
    with open(gpath) as f:
        g = json.load(f)
    nodes = {n["id"]: n for n in g["nodes"]}
    return g, nodes, g.get("links", [])


def folder_of(source_file, depth):
    parts = (source_file or "").split("/")
    if len(parts) <= 1:
        return source_file or "(external)"
    return "/".join(parts[: min(depth, len(parts) - 1)])


def git_head(path):
    try:
        return subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def cmd_stamp(args):
    print(json.dumps(stamp(args.repo), indent=2))


def stamp(repo):
    name, path = repo_path(repo)
    head = git_head(path)
    graph_commit = None
    gpath = os.path.join(path, "graphify-out", "graph.json")
    if os.path.isfile(gpath):
        # built_at_commit sits at the end of the file; avoid a full parse for the stamp
        with open(gpath, "rb") as f:
            f.seek(max(0, os.path.getsize(gpath) - 4096))
            tail = f.read().decode("utf-8", "ignore")
        marker = '"built_at_commit":'
        if marker in tail:
            graph_commit = tail.split(marker, 1)[1].split('"')[1]
    return {
        "repo": name,
        "commit": head,
        "graph_commit": graph_commit,
        "graph_stale": bool(head and graph_commit and head != graph_commit),
        "generated_at": datetime.date.today().isoformat(),
    }


def cmd_summary(args):
    name, path = repo_path(args.repo)
    g, nodes, links = load_graph(path)
    by_folder = collections.Counter(folder_of(n.get("source_file"), args.depth) for n in nodes.values())
    print(f"# {name}: {len(nodes)} nodes, {len(links)} edges, graph commit {g.get('built_at_commit', '?')[:9]}")
    print(f"\n## Nodes per folder (depth {args.depth})")
    for folder, count in by_folder.most_common(args.limit):
        print(f"{count:6d}  {folder}")
    comms = collections.defaultdict(list)
    for n in nodes.values():
        comms[(n.get("community"), n.get("community_name"))].append(n)
    print("\n## Largest communities (name: size, main folders)")
    for (cid, cname), members in sorted(comms.items(), key=lambda kv: -len(kv[1]))[:25]:
        top = collections.Counter(folder_of(m.get("source_file"), args.depth) for m in members).most_common(3)
        print(f"- [{cid}] {cname}: {len(members)} | " + ", ".join(f"{f} ({c})" for f, c in top))


def cmd_folder(args):
    name, path = repo_path(args.repo)
    _, nodes, links = load_graph(path)
    prefix = args.prefix.rstrip("/")
    inside = {i for i, n in nodes.items() if (n.get("source_file") or "").startswith(prefix)}
    if not inside:
        sys.exit(f"no nodes under '{prefix}' in {name}")
    files = collections.defaultdict(list)
    for i in inside:
        files[nodes[i]["source_file"]].append(nodes[i])
    print(f"# {name} :: {prefix}  ({len(files)} files, {len(inside)} nodes)\n\n## Files")
    for f in sorted(files)[: args.limit]:
        members = files[f]
        classes = sorted({m["label"] for m in members if m.get("_callable_class")})
        shown = classes or sorted({m["label"] for m in members if not m["label"].startswith(".")})[:3]
        print(f"- {f} ({len(members)}): {', '.join(shown[:5])}")
    if len(files) > args.limit:
        print(f"- ... {len(files) - args.limit} more files (raise --limit)")
    out_deps, in_deps = collections.Counter(), collections.Counter()
    for e in links:
        s, t, rel = e["source"], e["target"], e.get("relation")
        if rel in ("contains", "method", "defines"):
            continue
        if s in inside and t not in inside and t in nodes:
            out_deps[(rel, dep_label(nodes[t]))] += 1
        elif t in inside and s not in inside and s in nodes:
            in_deps[(rel, dep_label(nodes[s]))] += 1
    print("\n## Depends on (outside prefix)")
    for (rel, lbl), c in out_deps.most_common(args.limit):
        print(f"{c:5d}  {rel:12s} {lbl}")
    print("\n## Used by (outside prefix)")
    for (rel, lbl), c in in_deps.most_common(args.limit):
        print(f"{c:5d}  {rel:12s} {lbl}")


def dep_label(node):
    sf = node.get("source_file") or ""
    return sf if "/" in sf else f"{node['label']} (external)"


def cmd_file(args):
    name, path = repo_path(args.repo)
    _, nodes, links = load_graph(path)
    inside = {i for i, n in nodes.items() if n.get("source_file") == args.path}
    if not inside:
        sys.exit(f"no nodes for file '{args.path}' in {name}")
    print(f"# {name} :: {args.path}\n\n## Symbols")
    for i in sorted(inside, key=lambda i: line_no(nodes[i])):
        n = nodes[i]
        print(f"- {n['label']}  {n.get('source_location', '')}")
    edges = collections.Counter()
    for e in links:
        s, t = e["source"], e["target"]
        if e.get("relation") in ("contains", "method", "defines"):
            continue
        if s in inside and t not in inside and t in nodes:
            edges[("->", e["relation"], fmt(nodes[t]))] += 1
        elif t in inside and s not in inside and s in nodes:
            edges[("<-", e["relation"], fmt(nodes[s]))] += 1
    print("\n## Edges (-> outgoing, <- incoming)")
    for (d, rel, lbl), c in sorted(edges.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[1])):
        print(f"{d} {rel:12s} {lbl}" + (f"  x{c}" if c > 1 else ""))


def line_no(n):
    loc = n.get("source_location") or "L0"
    try:
        return int(loc.lstrip("L").split("-")[0])
    except ValueError:
        return 0


def fmt(n):
    sf = n.get("source_file") or ""
    return f"{n['label']} [{sf}]" if "/" in sf else f"{n['label']} (external)"


def cmd_search(args):
    name, path = repo_path(args.repo)
    _, nodes, _ = load_graph(path)
    term = args.term.lower()
    hits = [n for n in nodes.values()
            if term in (n.get("norm_label") or n["label"].lower()) or term in (n.get("source_file") or "").lower()]
    hits.sort(key=lambda n: (n.get("source_file") or "", line_no(n)))
    print(f"# {name}: {len(hits)} matches for '{args.term}'")
    for n in hits[: args.limit]:
        where = n.get("source_file") or "external"
        loc = n.get("source_location")
        print(f"- {n['label']}  [{where}{':' + loc if loc else ''}]  id={n['id']}")
    if len(hits) > args.limit:
        print(f"... {len(hits) - args.limit} more (raise --limit or narrow the term)")


def cmd_neighbors(args):
    name, path = repo_path(args.repo)
    _, nodes, links = load_graph(path)
    key = args.node
    ids = [key] if key in nodes else [i for i, n in nodes.items() if n["label"] == key or n.get("norm_label") == key.lower()]
    if not ids:
        sys.exit(f"no node '{key}' in {name}; try `search` first")
    ids = set(ids)
    rows = []
    for e in links:
        if args.relation and e.get("relation") != args.relation:
            continue
        if e["source"] in ids and e["target"] in nodes:
            rows.append(("->", e["relation"], fmt(nodes[e["target"]]), e.get("source_location", "")))
        elif e["target"] in ids and e["source"] in nodes:
            rows.append(("<-", e["relation"], fmt(nodes[e["source"]]), e.get("source_location", "")))
    print(f"# {name}: {len(rows)} edges for '{key}' ({len(ids)} matching node(s))")
    for d, rel, lbl, loc in rows[: args.limit]:
        print(f"{d} {rel:12s} {lbl} {loc}")
    if len(rows) > args.limit:
        print(f"... {len(rows) - args.limit} more (raise --limit or pass --relation)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stamp"); s.add_argument("repo"); s.set_defaults(fn=cmd_stamp)
    s = sub.add_parser("summary"); s.add_argument("repo"); s.add_argument("--depth", type=int, default=3)
    s.add_argument("--limit", type=int, default=40); s.set_defaults(fn=cmd_summary)
    s = sub.add_parser("folder"); s.add_argument("repo"); s.add_argument("prefix")
    s.add_argument("--limit", type=int, default=40); s.set_defaults(fn=cmd_folder)
    s = sub.add_parser("file"); s.add_argument("repo"); s.add_argument("path"); s.set_defaults(fn=cmd_file)
    s = sub.add_parser("search"); s.add_argument("repo"); s.add_argument("term")
    s.add_argument("--limit", type=int, default=40); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("neighbors"); s.add_argument("repo"); s.add_argument("node")
    s.add_argument("--relation"); s.add_argument("--limit", type=int, default=60); s.set_defaults(fn=cmd_neighbors)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
