---
name: implement
description: This skill should be used when the user asks to "implement <id>", "make the change for <id>", "apply the approved plan", "apply review fixes R-01 R-02 for <id>", or runs /nt-dev-coding:implement. Carries out ONE approved Nadi Tarangini plan (nt-docs/dev/<id>/APPROVED written by the approve hook) as minimal, surgical edits on the user's feature branch via the implementer agent, then runs safe local checks (php -l, flutter analyze --no-pub, dart format --output=none). Refuses when the task is not approved, a decision in the plan is still open, or a repo is on master, main or production. Never runs git writes, migrations or tests.
argument-hint: "<id> [fix R-01 R-02 ...]"
disable-model-invocation: true
allowed-tools: Read, Glob, Write, Edit, Bash(python3:*), Bash(php:*), Bash(flutter:*), Bash(dart:*), Bash(cd:*), Bash(cat:*), Bash(ls:*), Bash(wc:*), Bash(date:*), Agent, Task, AskUserQuestion
---

# implement: surgical edits for one approved task

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` first. `<docs>` is `$NT_DOCS_DIR` or `~/atreya-ai/nt-docs`.

## 1. Resolve the task and the mode

The first argument is the id; without one use `cat <docs>/dev/ACTIVE` and say which. If that is empty, `ls -t <docs>/dev` and ask.

| Situation | mode |
|---|---|
| `fix R-01 R-02 …` after the id | `fix round` for those review findings (copy their rows from `<docs>/dev/<id>/review.md`) |
| no implement.md | `implement` |
| implement.md has §3 rows not marked done | `resume` (continue from the first row not done) |
| every row done, no fix ids | ask: run a review (`/nt-dev-coding:review <id>`), or name the findings to fix |

## 2. Preflight (refuse unless ready)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/devtask.py" start <id>
```

Exit 1 means **refuse and stop**. Show `error` (no task folder) or the `blockers` verbatim, and what the user does about each:

- not approved / plan changed after approval / not active → the user types `approve <id>` (never create APPROVED or ACTIVE yourself, never suggest you can).
- a repo on `master`, `main`, `production` or a missing/detached HEAD → give the command for the user to run, e.g. `git -C <repos dir>/Ashoka-World-Backend checkout -b feature/<id>`, then re-run implement. Never run git yourself.

Exit 0: `base.json` holds each repo's base commit. If `warnings` lists files that were already uncommitted, tell the user they will appear as pre-existing (or "mixed" when the plan also changes them) and ask whether to continue or let them commit/stash first (they do the git). If they commit or stash and **no edit has been made yet** for this task, re-run `devtask.py start <id> --reset`; never use `--reset` after edits.

Read plan.md §9 "Needs your decision". If any item has no recorded answer, **refuse**: the plan must be re-planned (`/nt-dev-coding:task <id>`) and approved again; do not ask and continue.

## 3. Delegate to implementer

Start the **nt-dev-coding:implementer** agent with a prompt that begins:

```
plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>
docs_dir=<expanded docs dir>
task_dir=<docs_dir>/dev/<id>
repos=<repo>:<absolute root>@<branch>, ...
mode=implement | resume | fix round
findings=<fix round only: the copied review rows>
```

A hook denial during the run is a stop signal, not something to work around. The hooks enforce repos, not files: the agent itself keeps edits within plan `files:`.

## 4. Confirm the checks yourself

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/diffstat.py" <id> --json` to list the changed files (`--json` writes nothing; diff.md is written only by review). Check every changed `.php`/`.dart` file except those flagged `secret` or with status `D` (deleted), including `mixed` files. Files flagged `pre-existing` (the user's own earlier edits) may be checked too; their results are informational only.

- PHP (incl. Blade): `php -l <absolute path>`, one file at a time.
- Dart: `cd <app root> && flutter analyze --no-pub <paths relative to the app root>`, and `cd <app root> && dart format --output=none --set-exit-if-changed <paths>`.
  - `dart format` must pass for **new** files. For existing files it is informational: legacy files are often unformatted, and reformatting them is not allowed. Report which file it lists.

These commands write nothing. If a check fails on lines the task changed, start the implementer once more with `mode=fix round` and the check output as the finding, then run the checks again. If it fails only on untouched lines, record it as pre-existing.

Record the results in implement.md: append a "Checks (confirmed by implement skill, <date>)" section with Edit (command → exit code → relevant output lines). If implement.md does not exist (the agent stopped early), create it with Write using the front-matter from conventions.md. If `flutter`/`dart`/`php` is not installed, say so and record "not run".

## 5. Report

Tell the user: rows done/skipped/blocked, files changed with +/- (from the JSON), deviations, plan gaps, check results, unplanned / pre-existing / mixed files, and items "for the user" (migrations to run on staging, config keys). If there are plan gaps or real unplanned changes, suggest `/nt-dev-coding:task <id>` (re-plan; works for bugs too) and `approve <id>` again. Otherwise suggest `/nt-dev-coding:review <id>`. Do not commit, and do not suggest that you will.
