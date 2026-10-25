---
name: report
description: This skill should be used when the user asks to "write the test report", "give me the pass/fail summary", "export results for the workbook", "make the results CSV", "QA report for <run>", or runs /nt-qa-testing:report. Builds report.md (pass/fail summary with screenshot evidence) and results.csv rows in the user's NT_Web_QA_Sanity_Suite column order for one checked Nadi Tarangini QA run.
argument-hint: "[run-id]"
allowed-tools: Read, Glob, Write, Bash(ls:*), Bash(python3:*)
---

# report: summary with evidence plus workbook CSV

Produce `<docs>/qa/<run-id>/report.md` (layout: `references/report-template.md` in this skill folder) and `results.csv` (columns from `${CLAUDE_PLUGIN_ROOT}/references/workbook-columns.md`).

`<docs>` is `$NT_DOCS_DIR` or `~/atreya-ai/nt-docs`. Verdicts come only from `check.json` (result-checker); never re-judge a case or change a verdict here.

## 1. Resolve the run

Resolve the run per `${CLAUDE_PLUGIN_ROOT}/references/conventions.md`. Require `cases.md`, `run.json` and `check.json`. If `check.json` is missing but `run.json` exists, stop and suggest `/nt-qa-testing:run-web <run-id>` choosing **check only** (no re-execution). If nothing has run, suggest run-web. If `rerun-*` folders exist, mention them and offer their workbook rows (`results_csv.py <run_dir> --from rerun-<ts>`).

## 2. Build the CSV first (deterministic)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/results_csv.py" "<run_dir>"
```

The script prints a JSON summary. Report to the user:

- `unmapped_columns`: workbook headers with no known field (written empty). Suggest renaming them in `workbook-columns.md` or tell the user which field they likely mean.
- `cases_missing_from_check`: Ready cases with no verdict ("Not run"); mention them in the report.
- A refusal (production host found in a cell): show the message, name the source file to fix, and stop.

## 3. Write report.md

Read `plan.md` (title, scope), `cases.md`, `check.json`, `check.md` and `run.json`. Write the report per the template:

- headline verdict for the run (all Pass / N failures / blocked);
- totals table and per-priority split;
- **Failures first**: per Fail case, the failing step, expected vs observed, and screenshot links as relative markdown links (`screenshots/<file>.png`) so they open from the folder;
- Blocked and Skipped with reasons (rule ids for Skipped);
- all-cases table: id, scenario, priority, verdict, one-line actual;
- environment: base URL, run window (from run.json), roles used (names only), spec freshness from plan.md;
- for a bug run: any `[bug-repro]` case Fail → "bug reproduced"; all Pass → "not reproduced"; no Fail but some Blocked → "bug reproduction inconclusive: <reason>". If `retest-*/retest.md` exists, add "Latest retest (<ts>): <verdict>".

Never include credentials, account names, or personal data seen on staging.

## 4. Hand back

Show the headline, totals, failing case ids, and the paths of `report.md` and `results.csv`. Mention that the CSV is UTF-8 with BOM (opens correctly in Excel, including Marathi/Hindi text) and follows `references/workbook-columns.md`, which the user can edit to match the sheet.

## Additional resources

- **`references/report-template.md`**: report.md layout.
- **`${CLAUDE_PLUGIN_ROOT}/scripts/results_csv.py`**: CSV builder (`--from <retest-folder>` for retest rows).
