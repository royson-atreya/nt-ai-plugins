---
name: run-web
description: This skill should be used when the user asks to "run the test cases", "execute the cases on staging", "run the cases for <run-id>", "re-run TC-…-03", "check the evidence again", or runs /nt-qa-testing:run-web. Executes the Ready cases of an existing qa/<run-id>/cases.md on Nadi Tarangini web staging with the Playwright MCP tools (web-runner agent, screenshot per step), then has the independent result-checker agent compare evidence with expected results. Requires existing cases; for a new task or bug use plan.
argument-hint: "[run-id] [case ids to run, default all Ready]"
disable-model-invocation: true
allowed-tools: Read, Glob, Bash(ls:*), Bash(mv:*), Bash(mkdir:*), Bash(date:*), Agent, Task, AskUserQuestion, ToolSearch
---

# run-web: execute on staging, then check the evidence

Run the cases with the `web-runner` agent, then judge them with the `result-checker` agent in a fresh context. Stop after showing the mismatches; the report is a separate command.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` (run resolution, folder layout) and `${CLAUDE_PLUGIN_ROOT}/references/preflight.md` first. `<docs>` is `$NT_DOCS_DIR` or `~/atreya-ai/nt-docs`. Configured staging URL: `${user_config.staging_base_url}`.

## 1. Resolve the run and the mode

Resolve the run per conventions.md. Require `cases.md`; if missing, suggest `/nt-qa-testing:cases`. Then pick the mode:

| Situation | Mode | `out_dir` |
|---|---|---|
| no case ids given, no `run.json` yet | **full** | `run_dir` |
| no case ids given, `run.json` exists | ask: **overwrite** / **check only** (if `check.json` is missing) / cancel | `run_dir` |
| case ids given | **subset** | `run_dir/rerun-<ts>` (original evidence untouched) |

Overwrite: create `previous-<ts>/` with `mkdir` and `mv` into it `run.json`, `check.md`, `check.json`, `report.md`, `results.csv` and `screenshots/` (whichever exist). Check only: skip step 3.

## 2. Pre-flight

Run every check in `preflight.md` (base URL, Playwright, selection, roles preview, timestamp, confirm). For a subset, create `rerun-<ts>/screenshots/`.

## 3. Execute

Start the `nt-qa-testing:web-runner` agent. The prompt begins with:

```
plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>
docs_dir=<absolute docs dir>
run_dir=<absolute qa/<run-id> path>
out_dir=<run_dir, or the rerun folder>
base_url=<base URL>
case_ids=<comma-separated ids, or ALL_READY>
mode=run
```

followed by: "Execute these cases per web-runner instructions and write run.json in out_dir." Then apply the abort handling in `preflight.md`.

## 4. Independent check (fresh context)

Start the `nt-qa-testing:result-checker` agent with **only** paths, never the runner's summary or your own impressions:

```
plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>
run_dir=<absolute qa/<run-id> path>
out_dir=<same out_dir as step 3>
```

followed by: "Check every case in out_dir/run.json against run_dir/cases.md and write check.md and check.json in out_dir."

## 5. Hand back

Read `check.json` and show:

- any abort reason first;
- totals: Pass / Fail / Blocked / Skipped;
- each **Fail**: case id, first failing step, expected vs observed (one line), screenshot path;
- Blocked reasons grouped (e.g. "college account not configured: 3 cases");
- low-confidence verdicts.

Then suggest `/nt-qa-testing:report <run-id>`. For a subset run, say its results are in `rerun-<ts>/` (workbook rows: `results_csv.py <run_dir> --from rerun-<ts>`, which the report skill can run) and that `report.md` still reflects the full run. Do not write the report here and do not re-run failing cases automatically.

## Safety notes

- Hooks block production hosts, inject credentials from secure config, and mask them in output. Never work around a hook denial; report it.
- Never type real credentials or ask the user for them; placeholders only.
