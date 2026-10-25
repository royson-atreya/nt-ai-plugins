#!/usr/bin/env python3
"""Build results.csv for the NT_Web_QA_Sanity_Suite workbook.

Usage:
  results_csv.py <run_dir> [--from <subdir>]

Reads   <run_dir>/cases.md, <run_dir>/<subdir>/check.json, <run_dir>/<subdir>/run.json,
        and the column list in <plugin>/references/workbook-columns.md (section "## Columns").
Writes  <run_dir>/<subdir>/results.csv (UTF-8 with BOM so Excel shows Marathi/Hindi correctly).
        With --from (a retest folder) only the cases checked in that folder are written.

Credential placeholders become "<role> test account"; the script refuses to write if a cell
would contain a production host. Prints a JSON summary.
"""
import argparse
import csv
import json
import os
import re
import sys

sys.dont_write_bytecode = True

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACEHOLDER = re.compile(r"\{\{\s*nt-qa:([a-z]+):(username|password)\s*\}\}")
PROD = re.compile(r"(?i)(?<![a-z0-9.-])((?:[a-z0-9-]+\.)*(?:naditarangini\.com|ashoka\.world))(?![a-z0-9-])")
STAGING = {"staging-dashboard.naditarangini.com", "staging-api.ashoka.world"}

ALIASES = {
    "id": ["testcaseid", "tcid", "caseid", "id", "testid"],
    "module": ["module"],
    "sub_module": ["submodule", "screen", "feature"],
    "scenario": ["testscenario", "scenario", "title", "testcasetitle", "description"],
    "preconditions": ["preconditions", "precondition", "prerequisites"],
    "steps": ["teststeps", "steps"],
    "test_data": ["testdata", "data"],
    "expected": ["expectedresult", "expected", "expectedresults"],
    "actual": ["actualresult", "actual", "actualresults"],
    "status": ["status", "result", "passfail"],
    "priority": ["priority"],
    "remarks": ["remarks", "comments", "notes", "comment"],
    "bug_id": ["bugid", "defectid", "bug", "defect"],
    "run_date": ["executiondate", "date", "rundate", "testeddate"],
    "environment": ["environment", "env"],
    "evidence": ["evidence", "screenshot", "screenshots", "attachment"],
}
FIELD_OF = {alias: field for field, names in ALIASES.items() for alias in names}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def columns():
    text = open(os.path.join(PLUGIN, "references", "workbook-columns.md"), encoding="utf-8").read()
    sec = re.search(r"^## Columns\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    cols = [c.strip() for c in re.findall(r"^-\s+(.+?)\s*$", sec.group(1) if sec else "", re.M)]
    if not cols:
        sys.exit("workbook-columns.md has no bullets under '## Columns'")
    return cols


def parse_cases(path):
    text = open(path, encoding="utf-8").read()
    cases = {}
    for block in re.split(r"(?m)^(?=## TC-)", text):
        head = re.match(r"## (TC-\S+)\s*[·\-–]\s*(.*)", block)
        if not head:
            continue
        # a case ends at the next heading or bold section (Traceability, Open questions, ...)
        lines = block.splitlines()
        end = next((i for i, l in enumerate(lines[1:], 1) if re.match(r"#{1,6} |\*\*[A-Z]", l)), len(lines))
        block = "\n".join(lines[:end])
        cid, title = head.group(1), head.group(2).strip()
        c = {"id": cid, "bug_repro": "[bug-repro]" in title,
             "scenario": title.replace("[bug-repro]", "").strip()}
        for k, v in re.findall(r"(?m)^-\s+([A-Za-z\- ]+):\s*(.*)$", block):
            c[norm(k)] = v.strip()
        steps = re.findall(r"(?m)^\s*(\d+)\.\s+(.*?)(?:\s*→\s*Expected:\s*(.*))?$", block)
        c["steps"] = "\n".join(f"{n}. {a.strip()}" for n, a, _ in steps)
        c["step_expected"] = "\n".join(f"{n}. {e.strip()}" for n, _, e in steps if e)
        m = re.search(r"(?m)^Expected result:\s*(.+)$", block)
        c["expected"] = m.group(1).strip() if m else c["step_expected"]
        cases[cid] = c
    return cases


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def scrub(value):
    return PLACEHOLDER.sub(lambda m: f"{m.group(1)} test account", value or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--from", dest="sub", default=".")
    a = ap.parse_args()
    run_dir = os.path.realpath(os.path.expanduser(a.run_dir))
    out_dir = os.path.realpath(os.path.join(run_dir, a.sub))
    run_id = os.path.basename(run_dir)

    cases = parse_cases(os.path.join(run_dir, "cases.md"))
    check = {c["id"]: c for c in load(os.path.join(out_dir, "check.json")).get("cases", [])}
    run = load(os.path.join(out_dir, "run.json"))
    shots = {c["id"]: next((s.get("screenshot") for s in c.get("steps", []) if s.get("screenshot")), "")
             for c in run.get("cases", [])}
    run_date = (run.get("started_at") or "")[:10]
    bug_like = bool(re.match(r"^[A-Z][A-Z0-9]*-(?:BUG-)?\d+$", run_id))

    ids = list(check) if a.sub != "." else list(cases)
    cols = columns()
    fields = [FIELD_OF.get(norm(c)) for c in cols]
    rows, counts = [], {}
    for cid in ids:
        c, k = cases.get(cid, {"id": cid}), check.get(cid, {})
        status_md = c.get("status", "")
        if k:
            status = k.get("verdict", "")
        elif status_md.startswith(("Skipped", "Blocked")):
            status = status_md.split(" ", 1)[0]
        else:
            status = "Not run"
        counts[status] = counts.get(status, 0) + 1
        remarks = []
        if status in ("Skipped", "Blocked"):
            reason = status_md if status_md.startswith(status) else k.get("actual", "")
            if reason:
                remarks.append(reason)
        evidence = shots.get(cid, "")
        if k.get("failed_step"):
            mm = next((m for m in k.get("mismatches", []) if m.get("step") == k["failed_step"]), {})
            remarks.append(f"Step {k['failed_step']}: expected: {mm.get('expected', '')} | observed: {mm.get('observed', '')}")
            evidence = mm.get("evidence") or evidence
        if k.get("confidence") and k.get("confidence") != "high":
            remarks.append(f"confidence {k['confidence']}")
        if c.get("bug_repro"):
            remarks.append(f"bug repro ({run_id})")
        if evidence and a.sub != ".":
            evidence = os.path.join(a.sub.strip("/"), evidence)
        if evidence and status == "Fail":
            remarks.append(f"evidence {evidence}")
        values = {
            "id": cid, "module": c.get("module", ""), "sub_module": c.get("submodule", ""),
            "scenario": c.get("scenario", ""), "preconditions": c.get("preconditions", ""),
            "steps": c.get("steps", ""), "test_data": c.get("testdata", ""), "expected": c.get("expected", ""),
            "actual": k.get("actual", "" if status != "Not run" else "not executed"),
            "status": status, "priority": c.get("priority", ""), "remarks": "; ".join(remarks),
            "bug_id": run_id if (c.get("bug_repro") or bug_like) else "", "run_date": run_date,
            "environment": "web-staging", "evidence": evidence,
        }
        rows.append([scrub(values.get(f, "")) if f else "" for f in fields])

    for row in rows:
        for cell in row:
            for h in PROD.findall(cell):
                if h.lower() not in STAGING:
                    sys.exit(f"refusing to write results.csv: a cell mentions production host '{h}'. Fix the source file.")

    out = os.path.join(out_dir, "results.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    print(json.dumps({"csv": out, "rows": len(rows), "by_status": counts,
                      "unmapped_columns": [c for c, f in zip(cols, fields) if not f],
                      "cases_missing_from_check": [i for i in cases if i not in check and a.sub == "."
                                                   and not cases[i].get("status", "").startswith(("Skipped", "Blocked"))]},
                     indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
