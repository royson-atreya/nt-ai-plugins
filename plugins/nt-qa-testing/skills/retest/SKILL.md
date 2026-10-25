---
name: retest
description: This skill should be used when the user asks to "retest bug <id>", "is <bug> fixed", "verify the fix for <bug>", "re-run the bug cases", "check if the bug still happens on staging", or runs /nt-qa-testing:retest. Re-runs only the [bug-repro] cases of an existing qa/<bug-id>/ bug run on Nadi Tarangini web staging (web-runner, then result-checker in a fresh context) and gives a FIXED / NOT FIXED / INCONCLUSIVE verdict with evidence. Requires an existing bug run with [bug-repro] cases.
argument-hint: "<bug-id> [note, e.g. build or deploy version]"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Write, Bash(ls:*), Bash(mkdir:*), Bash(date:*), Bash(python3:*), Agent, Task, AskUserQuestion, ToolSearch
---

# retest: is the bug fixed?

Re-run only the bug's `[bug-repro]` cases into a new `retest-<ts>/` folder inside the run, check them independently, and write `retest.md` with the verdict. Never edit the original run's files.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` and `${CLAUDE_PLUGIN_ROOT}/references/preflight.md` first. `<docs>` is `$NT_DOCS_DIR` or `~/atreya-ai/nt-docs`. Configured staging URL: `${user_config.staging_base_url}`.

## 1. Find the bug run

- With no argument, use the most recent folder in `<docs>/qa/` whose `plan.md` front-matter has `kind: bug`.
- If `qa/<arg>/` does not exist, Grep `qa/*/bug.md` and `qa/*/plan.md` for the id (bug runs without an id use a slug). If still nothing, list folders with `kind: bug` and ask; if there are none, suggest `/nt-qa-testing:plan <bug report>`.
- If the run's kind is not `bug`, stop: "retest is for bug runs; use `/nt-qa-testing:run-web <run-id> <case ids>`."
- Collect the `[bug-repro]` case ids whose status is Ready. If none, stop.
- Note the original verdicts of those ids from `qa/<bug-id>/check.json` (else "never run"), and the verdict of the latest earlier `retest-*/retest.md`, if any.

## 2. Pre-flight

Run every check in `preflight.md`. Then create `qa/<bug-id>/retest-<ts>/screenshots/`.

## 3. Run and check

1. Start `nt-qa-testing:web-runner` with:
   ```
   plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>
   docs_dir=<absolute docs dir>
   run_dir=<absolute qa/<bug-id> path>
   out_dir=<absolute retest folder path>
   base_url=<base URL>
   case_ids=<repro ids>
   mode=retest
   ```
   and "Execute these cases per web-runner instructions and write run.json in out_dir." Apply the abort handling in `preflight.md`; an abort with nothing executed means verdict INCONCLUSIVE (write retest.md with the reason and stop).
2. Start `nt-qa-testing:result-checker` with only `plugin_root`, `run_dir`, `out_dir` (the retest folder), and "Check every case in out_dir/run.json against run_dir/cases.md. These are [bug-repro] cases: their expected result is the correct behaviour, so Pass means the bug no longer reproduces."
3. Build retest rows for the workbook:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/results_csv.py" "<run_dir>" --from "retest-<ts>"
   ```

## 4. Verdict

From the retest `check.json` (missing `check.json` → INCONCLUSIVE):

| Verdict | Rule |
|---|---|
| **FIXED** | every repro case Pass |
| **NOT FIXED** | the main repro case (lowest id) Fail |
| **NOT FIXED (partial: <ids>)** | main repro case Pass, but a repro variant Fail |
| **INCONCLUSIVE** | no Fail, but at least one Blocked (say why: role missing, staging down, insufficient evidence) |

Write `retest-<ts>/retest.md`: front-matter (`generated_by: nt-qa-testing/retest`, per conventions.md), verdict line, the user's note (build/version) if given, a table per repro case (id, original verdict, previous retest verdict, this retest's verdict, first failing step, screenshot link), and for NOT FIXED the expected vs observed of the failing step.

## 5. Hand back

Show the verdict prominently, the before/after table, the failing-step evidence for NOT FIXED, and the paths of `retest.md` and the retest `results.csv`. When FIXED and the bug run has P3 regression cases, suggest `/nt-qa-testing:run-web <bug-id>` for the full suite.
