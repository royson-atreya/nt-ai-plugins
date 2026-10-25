#!/usr/bin/env python3
"""Extract, validate and total the 'Proposed work items' block of an impact report.

Usage:
  work_items.py check  <impact-report.md>          validate the schema and print totals per discipline (exit 1 on errors)
  work_items.py show   <impact-report.md>          print stories/tasks as a compact table (for approval)
  work_items.py extract <impact-report.md>         print the JSON block
  work_items.py update <impact-report.md> <json>   replace the block with the JSON in <json> (a file path)
  work_items.py tasklist <impact-report.md> <out.md>  write a plain task-list file (fallback when there is no Zoho connector)

See references/work-items-schema.md.
"""
import collections
import json
import re
import sys

START, END = "<!-- nt-work-items:start -->", "<!-- nt-work-items:end -->"
DISCIPLINES = {"backend", "web", "app", "qa", "devops", "design"}
BLOCK = re.compile(re.escape(START) + r"\s*```json\s*(.*?)\s*```\s*" + re.escape(END), re.S)


def read_block(path):
    with open(path) as f:
        text = f.read()
    m = BLOCK.search(text)
    if not m:
        sys.exit(f"error: no work-items block ({START} ... {END}) in {path}")
    return text, m, json.loads(m.group(1))


def validate(wi):
    errs = []
    if wi.get("schema_version") != 1:
        errs.append("schema_version must be 1")
    if wi.get("estimate_unit") != "person-days":
        errs.append("estimate_unit must be person-days")
    keys = collections.Counter()
    for s in wi.get("stories", []):
        keys[s.get("key")] += 1
        for f in ("key", "title", "description", "modules", "priority", "acceptance_criteria", "tasks"):
            if f not in s:
                errs.append(f"story {s.get('key')}: missing {f}")
        if s.get("priority") not in ("high", "medium", "low"):
            errs.append(f"story {s.get('key')}: priority must be high|medium|low")
        if not any(t.get("discipline") == "qa" for t in s.get("tasks", [])):
            errs.append(f"story {s.get('key')}: needs at least one qa task")
        for t in s.get("tasks", []):
            keys[t.get("key")] += 1
            if t.get("discipline") not in DISCIPLINES:
                errs.append(f"task {t.get('key')}: discipline must be one of {sorted(DISCIPLINES)}")
            est = t.get("estimate_days") or {}
            if not (isinstance(est.get("min"), (int, float)) and isinstance(est.get("max"), (int, float)) and 0 < est["min"] <= est["max"]):
                errs.append(f"task {t.get('key')}: estimate_days needs 0 < min <= max")
    errs += [f"duplicate key {k}" for k, c in keys.items() if c > 1]
    if not wi.get("stories"):
        errs.append("no stories")
    return errs


def totals(wi):
    per = collections.defaultdict(lambda: [0.0, 0.0])
    for s in wi.get("stories", []):
        for t in s.get("tasks", []):
            e = t.get("estimate_days") or {}
            per[t.get("discipline")][0] += e.get("min", 0)
            per[t.get("discipline")][1] += e.get("max", 0)
    tmin, tmax = sum(v[0] for v in per.values()), sum(v[1] for v in per.values())
    c = wi.get("contingency_pct", 20) / 100
    return per, (tmin, tmax), (round(tmin * (1 + c), 1), round(tmax * (1 + c), 1))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(0)
    cmd, path = sys.argv[1], sys.argv[2]
    text, m, wi = read_block(path)
    if cmd == "extract":
        print(json.dumps(wi, indent=2))
    elif cmd == "check":
        errs = validate(wi)
        per, (tmin, tmax), (cmin, cmax) = totals(wi)
        print(f"stories: {len(wi.get('stories', []))}, tasks: {sum(len(s.get('tasks', [])) for s in wi.get('stories', []))}, status: {wi.get('status')}")
        for d, (a, b) in sorted(per.items()):
            print(f"  {d:<8} {a:g}-{b:g} d")
        print(f"  total    {tmin:g}-{tmax:g} d; with {wi.get('contingency_pct', 20)}% contingency {cmin:g}-{cmax:g} d")
        for e in errs:
            print("ERROR", e)
        sys.exit(1 if errs else 0)
    elif cmd == "show":
        for s in wi["stories"]:
            print(f"{s['key']} [{s['priority']}] {s['title']}  ({', '.join(s['modules'])})")
            for t in s["tasks"]:
                e = t["estimate_days"]
                print(f"   {t['key']:<8} {t['discipline']:<8} {e['min']:g}-{e['max']:g}d  {t['title']}")
    elif cmd == "update":
        with open(sys.argv[3]) as f:
            new = json.load(f)
        errs = validate(new)
        if errs:
            print("\n".join("ERROR " + e for e in errs))
            sys.exit(1)
        block = f"{START}\n```json\n{json.dumps(new, indent=2)}\n```\n{END}"
        with open(path, "w") as f:
            f.write(text[: m.start()] + block + text[m.end():])
        print(f"updated work items in {path}")
    elif cmd == "tasklist":
        out = sys.argv[3]
        per, (tmin, tmax), (cmin, cmax) = totals(wi)
        lines = [f"# Task list: {wi.get('change_request', '')}", "",
                 f"Source: `{wi.get('impact_report', path)}`. Estimate {tmin:g}-{tmax:g} person-days "
                 f"({cmin:g}-{cmax:g} with {wi.get('contingency_pct', 20)}% contingency).",
                 "", "> Created because no Zoho Sprints connector was available. Import these into Zoho Sprints project P7 by hand.", ""]
        for s in wi["stories"]:
            lines += [f"## {s['key']}: {s['title']} ({s['priority']})", "", s["description"], "",
                      "**Modules:** " + ", ".join(s["modules"]), "", "**Acceptance criteria:**"]
            lines += [f"- [ ] {a}" for a in s["acceptance_criteria"]]
            lines += ["", "**Tasks:**"]
            for t in s["tasks"]:
                e = t["estimate_days"]
                lines.append(f"- [ ] `{t['key']}` [{t['discipline']}] {t['title']} ({e['min']:g}-{e['max']:g} d)")
            lines.append("")
        with open(out, "w") as f:
            f.write("\n".join(lines))
        print(f"wrote {out}")
    else:
        sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
