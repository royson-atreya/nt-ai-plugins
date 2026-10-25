#!/usr/bin/env python3
"""Check, render, confirm and index module-map.json files (see references/module-map-schema.md).

Usage:
  module_map.py check   <repo>        schema + coverage + overlap report (exit 1 on errors)
  module_map.py render  <repo>        write module-map.md from module-map.json
  module_map.py confirm <repo>        set status=confirmed, confirmed_at=today, re-render
  module_map.py index                 write $NT_DOCS_DIR/module-index.md from all repo maps
  module_map.py owner   <repo> <path> which module owns a file

Env: NT_DOCS_DIR (default ~/atreya-ai/nt-docs), NT_REPOS_DIR (default ~/atreya-ai/repos).
"""
import collections
import datetime
import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph_query import load_graph, repo_path  # noqa: E402

PRODUCT_AREAS = {"NadiTarangini", "NadiPariksha", "Turyaa", "Guna", "ENACH", "MedicalInventory",
                 "ResearchDashboard", "Organization", "NTAdmin", "NTUser", "External", "V1", "Core", "Shared"}
KINDS = {"product-area", "core", "feature", "shared", "infra"}
STATUSES = {"live", "not-in-use", "unknown"}
REQUIRED = ("id", "name", "product_area", "kind", "status", "summary", "paths", "entry_points",
            "route_prefixes", "route_count", "external_systems", "depends_on", "inferred", "evidence", "notes")
CODE_ROOTS = {
    "Ashoka-World-Backend": ("app/", "resources/views/", "routes/"),
    "Nadi-Tarangini-Frontend": ("app/", "resources/views/", "routes/", "public/js/"),
    "Nadi-Tarangini-App": ("lib/",),
}
SKIP = re.compile(r"(\.min\.js$|/vendor/|/plugins?/|jquery|bootstrap|jspdf|chart(\.|js))", re.I)
REPOS_ORDER = ("Ashoka-World-Backend", "Nadi-Tarangini-Frontend", "Nadi-Tarangini-App")


def docs_dir():
    return os.path.expanduser(os.environ.get("NT_DOCS_DIR", "~/atreya-ai/nt-docs"))


def map_path(repo_name, ext="json"):
    return os.path.join(docs_dir(), repo_name, f"module-map.{ext}")


def load_map(repo_name):
    p = map_path(repo_name)
    if not os.path.isfile(p):
        sys.exit(f"error: no module map at {p}; run the map skill first")
    with open(p) as f:
        return json.load(f)


def owner(modules, path):
    best, best_len, ties = None, -1, []
    for m in modules:
        for pat in m.get("paths", []):
            if fnmatch.fnmatch(path, pat):
                if len(pat) > best_len:
                    best, best_len, ties = m["id"], len(pat), [m["id"]]
                elif len(pat) == best_len and m["id"] not in ties:
                    ties.append(m["id"])
    return best, ties


def code_files(repo_name, repo_dir):
    _, nodes, _ = load_graph(repo_dir)
    roots = CODE_ROOTS.get(repo_name, ("",))
    files = {n.get("source_file") for n in nodes.values() if n.get("file_type") == "code"}
    return sorted(f for f in files if f and f.startswith(roots) and not SKIP.search(f))


def cmd_check(repo):
    name, path = repo_path(repo)
    mm = load_map(name)
    errors, warnings = [], []
    if mm.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if mm.get("status") not in ("draft", "confirmed"):
        errors.append("status must be draft|confirmed")
    if mm.get("repo") != name:
        errors.append(f"repo must be {name}")
    ids = collections.Counter(m.get("id") for m in mm.get("modules", []))
    for i, c in ids.items():
        if c > 1:
            errors.append(f"duplicate module id: {i}")
    for m in mm.get("modules", []):
        mid = m.get("id", "?")
        missing = [k for k in REQUIRED if k not in m]
        if missing:
            errors.append(f"{mid}: missing fields {missing}")
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", mid):
            errors.append(f"{mid}: id must be kebab-case")
        if m.get("product_area") not in PRODUCT_AREAS:
            errors.append(f"{mid}: product_area '{m.get('product_area')}' not in {sorted(PRODUCT_AREAS)}")
        if m.get("kind") not in KINDS:
            errors.append(f"{mid}: kind must be one of {sorted(KINDS)}")
        if m.get("status") not in STATUSES:
            errors.append(f"{mid}: status must be one of {sorted(STATUSES)}")
        for dep in m.get("depends_on", []):
            if dep not in ids:
                warnings.append(f"{mid}: depends_on unknown module '{dep}'")
    files = code_files(name, path)
    unassigned, overlaps, per_module = [], [], collections.Counter()
    for f in files:
        best, ties = owner(mm.get("modules", []), f)
        if best is None:
            unassigned.append(f)
        elif len(ties) > 1:
            overlaps.append((f, ties))
        else:
            per_module[best] += 1
    for m in mm.get("modules", []):
        if per_module[m["id"]] == 0 and not any(o for o in overlaps if m["id"] in o[1]):
            warnings.append(f"{m['id']}: owns no files (check its paths)")
    cov = 100.0 * (len(files) - len(unassigned)) / max(1, len(files))
    for f, ties in overlaps[:30]:
        errors.append(f"overlap: {f} matched equally by {ties}")
    print(f"# {name} module map: {len(mm.get('modules', []))} modules, status={mm.get('status')}, "
          f"commit {str(mm.get('commit'))[:9]}")
    print(f"coverage: {len(files) - len(unassigned)}/{len(files)} code files ({cov:.1f}%)  "
          f"errors: {len(errors)}  warnings: {len(warnings)}")
    for e in errors:
        print(f"ERROR {e}")
    for w in warnings:
        print(f"WARN  {w}")
    print("\nfiles per module:")
    for mid, c in per_module.most_common():
        print(f"  {c:5d}  {mid}")
    if unassigned:
        dirs = collections.Counter(os.path.dirname(f) for f in unassigned)
        print(f"\nunassigned ({len(unassigned)} files), by folder:")
        for d, c in dirs.most_common(30):
            print(f"  {c:4d}  {d}/")
    return errors


def cmd_render(repo):
    name, _ = repo_path(repo)
    mm = load_map(name)
    status = mm["status"].upper()
    lines = [
        "---",
        "generated_by: nt-documentation/map",
        f"generated_at: {mm.get('generated_at')}",
        f"status: {mm['status']}",
        "sources:",
        f"  - repo: {name}",
        f"    commit: {mm.get('commit')}",
        f"    graph_commit: {mm.get('graph_commit')}",
        "---",
        "",
        f"# Module map: {name} ({status})",
        "",
        "> Generated from `module-map.json` by `module_map.py render`. Edit the JSON, not this file.",
    ]
    if mm["status"] == "draft":
        lines.append("> **Draft.** The module list has not been confirmed yet, so do not treat it as verified context.")
    lines += ["", "| Module | Area | Kind | Status | Routes | Entry points | Summary |", "|---|---|---|---|---|---|---|"]
    for m in mm["modules"]:
        flag = " *(inferred)*" if m.get("inferred") else ""
        lines.append(f"| `{m['id']}` {m['name']}{flag} | {m['product_area']} | {m['kind']} | {m['status']} | "
                     f"{m.get('route_count', 0)} | {', '.join(m.get('entry_points', [])[:4])} | {m.get('summary', '')} |")
    lines += ["", "## Modules", ""]
    for m in mm["modules"]:
        lines += [f"### `{m['id']}` {m['name']}", "", m.get("summary", ""), ""]
        lines.append(f"- **Paths:** " + ", ".join(f"`{p}`" for p in m.get("paths", [])))
        if m.get("route_prefixes"):
            lines.append(f"- **Route prefixes ({m.get('route_count', 0)} routes):** " + ", ".join(f"`{p}`" for p in m["route_prefixes"]))
        if m.get("external_systems"):
            lines.append("- **External systems:** " + ", ".join(m["external_systems"]))
        if m.get("depends_on"):
            lines.append("- **Depends on:** " + ", ".join(f"`{d}`" for d in m["depends_on"]))
        lines.append("- **Evidence:** " + "; ".join(f"`{e}`" for e in m.get("evidence", [])))
        if m.get("notes"):
            lines.append(f"- **Notes:** {m['notes']}")
        lines.append("")
    out = map_path(name, "md")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {out}")


def cmd_confirm(repo):
    if cmd_check(repo):
        sys.exit("refusing to confirm: fix the errors above first")
    name, _ = repo_path(repo)
    mm = load_map(name)
    mm["status"] = "confirmed"
    mm["confirmed_at"] = datetime.date.today().isoformat()
    with open(map_path(name), "w") as f:
        json.dump(mm, f, indent=2)
        f.write("\n")
    cmd_render(repo)


def cmd_index():
    maps = {}
    for name in REPOS_ORDER:
        p = map_path(name)
        if os.path.isfile(p):
            with open(p) as f:
                maps[name] = json.load(f)
    if not maps:
        sys.exit("error: no module maps found")
    by_area = collections.defaultdict(lambda: collections.defaultdict(list))
    for name, mm in maps.items():
        for m in mm["modules"]:
            by_area[m["product_area"]][name].append(m["id"])
    cols = [n for n in REPOS_ORDER if n in maps]
    lines = ["---", "generated_by: nt-documentation/map", f"generated_at: {datetime.date.today().isoformat()}", "sources:"]
    for n in cols:
        lines += [f"  - repo: {n}", f"    commit: {maps[n].get('commit')}", f"    status: {maps[n].get('status')}"]
    lines += ["---", "", "# Module index across repos", "",
              "| Product area | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for area in sorted(by_area):
        lines.append(f"| {area} | " + " | ".join(", ".join(f"`{i}`" for i in by_area[area].get(n, [])) or "-" for n in cols) + " |")
    out = os.path.join(docs_dir(), "module-index.md")
    os.makedirs(docs_dir(), exist_ok=True)
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {out}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "index":
        return cmd_index()
    if not args:
        sys.exit(f"usage: module_map.py {cmd} <repo>")
    if cmd == "owner":
        name, _ = repo_path(args[0])
        best, ties = owner(load_map(name)["modules"], args[1])
        print(best if len(ties) <= 1 else f"OVERLAP {ties}")
        return
    if cmd == "check":
        sys.exit(1 if cmd_check(args[0]) else 0)
    {"render": cmd_render, "confirm": cmd_confirm}.get(cmd, lambda _: sys.exit(f"unknown command {cmd}"))(args[0])


if __name__ == "__main__":
    main()
