# nt-dev-coding conventions

Every skill and agent in this plugin follows these rules. Read this file before doing any work.

## Paths

| What | Default | Override |
|---|---|---|
| Specs (input, written by nt-documentation) | `~/atreya-ai/nt-docs` | `NT_DOCS_DIR` |
| Task folder (output) | `~/atreya-ai/nt-docs/dev/<id>/` | follows `NT_DOCS_DIR` |
| Product repos | `~/atreya-ai/repos` | `NT_REPOS_DIR` |

| Alias | Repo folder | Stack | Checks after an edit |
|---|---|---|---|
| `backend` | `Ashoka-World-Backend` | Laravel 10 API, MySQL. **Its `.env` points at the PRODUCTION database.** | `php -l <file>` per changed `.php` |
| `web` | `Nadi-Tarangini-Frontend` | Laravel 8 + Blade, calls the backend via `config('app.backend_url')` | `php -l <file>` per changed `.php` (Blade: syntax of PHP blocks only) |
| `app` | `Nadi-Tarangini-App` | Flutter + BLoC, code in `lib/` | `flutter analyze --no-pub <files>`, `dart format --output=none --set-exit-if-changed <files>` |

- `devtask.py ...` / `diffstat.py ...` in skills and agents is shorthand for `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py" ...`.
- When a skill starts an agent, the agent prompt **always** begins with `plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>`, `docs_dir=<expanded docs dir>`, `task_dir=<docs_dir>/dev/<id>`, then the task inputs. Agents may not see `${CLAUDE_PLUGIN_ROOT}` expanded. Skills start the agents by their namespaced names: `nt-dev-coding:change-planner`, `nt-dev-coding:implementer`, `nt-dev-coding:code-reviewer`.
- Timestamps come from `date`; never guess the time.

## Hard rules

1. **One task or bug at a time.** Only the approved one is implemented.
2. **Only the user approves.** Approval exists when the user types `approve <id>`; a hook writes `dev/<id>/APPROVED` and `dev/ACTIVE`. Never create, edit or delete those files, never type the approval on the user's behalf, and never treat "looks good" as approval. Only a prompt that is exactly `approve <id>` counts; for near-misses, repeat the exact form. `revoke <id>` withdraws it. On the approval turn, reply only that the next step is `/nt-dev-coding:implement <id>`; never edit the repos outside the implement skill.
3. **The user does all git actions.** Only read-only git runs (a hook allowlists it). Never run commit, push, pull, checkout, switch, branch (except listing), merge, rebase, reset, stash, tag, add, restore, fetch, config writes, remote changes or symbolic-ref. When a repo is on `master`, `main` or `production`, tell the user the exact command, e.g. `git -C ~/atreya-ai/repos/Ashoka-World-Backend checkout -b feature/<id>`, and stop. Read-only git (`status`, `diff`, `log`, `show`, `blame`, `rev-parse`) is fine.
4. **Never touch the production database.** `php artisan` only `route:list`, `list`, `about`, `--version`. Never migrate, `db:*`, tinker, seed, queue, schedule, test, cache or config commands; no phpunit/pest/sail; no `php -r`. A migration the plan needs is written as a **new file** and listed in handoff for the user to run on staging.
5. **No new dependencies without asking.** No composer/npm/yarn/pod/flutter pub installs, upgrades or publishing (hooks block them). If a change seems to need a package, stop and ask; the user installs it.
6. **Surgical edits only.** See "Large files" below. Never rewrite, reformat or reorder code the task does not need. `Write` creates new files only; existing files change with `Edit`.
7. **Never read secrets**: `.env*`, `*.jks`, `*.keystore`, `firebase-*.json`, `google-services.json`, `GoogleService-Info.plist`. Config such as `config/services.php` may be read for key names only. Never write credentials into code or docs.
8. **No patient data.** Never query databases, never copy names, phones, emails, readings or report contents from code, fixtures, logs or screens. Test data is visibly fake (see nt-qa-testing conventions: `QA-AUTO …`, `qa.auto+<tag>@example.com`, `90000xxxxx`).
9. **Plan from specs.** Use nt-docs first (impact report, module analysis, api-links, module maps), then confirm in code. If `devtask.py specs` returns `gate: stop`, stop and suggest `/nt-documentation:impact "<change>"`.
10. **Searches in the repos are limited to code types** (Grep `type: "php"` / `"dart"` or `glob: "*.php"`; `grep -r --include='*.php'`; `rg -t php`). Several secret files are committed; an open search could print them.

## Large files

Some files are 5,000–13,000 lines (big controllers, Blade views, Dart screens).

- Before opening a file, run `wc -l <file>`. Over 800 lines: never Read it whole.
- Find the place with `Grep -n` (code type set) for the function, route or widget name; then Read with `offset`/`limit` (≤ 200 lines) around it.
- `Edit` with an `old_string` that is unique and as short as possible (the changed lines plus 1–3 lines of context). Keep the file's indentation (tabs vs spaces), quoting and naming style.
- One logical change per Edit. No drive-by fixes, renames, import sorting, whitespace or comment churn.

## Task id and folder

- Id: a ticket id found in the input (`ZS-1234`, `NT-BUG-142`), else `<YYYYMMDD>-<slug>` (max 6 words). `devtask.py id "<text>"` computes it.
- Later skills take the id as the first argument. Without one, use `cat <docs>/dev/ACTIVE`; if empty, list `ls -t <docs>/dev` and ask.

```
dev/
├── ACTIVE                 # hook-written: the active task id
└── <id>/
    ├── bug.md             # bug: the user's report, verbatim (secrets/PII removed by asking)
    ├── ticket.md          # task|bug: ticket text
    ├── plan.md            # task|bug: change plan (front-matter repos:/files: drive the hooks and diffstat)
    ├── APPROVED           # hook-written on `approve <id>`: repos snapshot + plan sha256
    ├── base.json          # implement: base commit + pre-existing changes per repo (devtask.py start)
    ├── implement.md       # implement: edit log, deviations, check results
    ├── diff.md            # review: diffstat.py
    ├── review.md          # review: code-reviewer
    └── handoff.md         # handoff
```

Every markdown file (including diff.md, review.md and handoff.md) starts with front-matter:

```yaml
---
generated_by: nt-dev-coding/<skill or agent>
generated_at: <ISO timestamp>
task_id: <id>
kind: task | bug
---
```

## ticket.md format

```markdown
# <Title: imperative, ≤ 80 chars>

**Type:** Task | Bug · **Priority:** P1|P2|P3 · **Repos:** <aliases> · **Estimate:** <x–y> person-days

## Requirement
<one paragraph: what must be true after the change, in product terms>

## Description
<context, who is affected (roles), screens/APIs involved, spec links (docs-relative paths)>

## Reproduction steps            (bug only)
1. ...
**Expected:** ... **Actual:** ...  **Environment:** web staging | app <flavor> | backend

## Suspected root cause          (bug only)
<file:line and reasoning; mark (inferred) where not confirmed>

## Acceptance criteria
- AC-1: Given <state>, when <action>, then <observable result>.
- AC-2: ...
(bug: AC-1 is always "the reproduction steps no longer reproduce the bug")

## Out of scope
- ...
```

## plan.md format

Front-matter keys `repos` and `files` are **machine-read**. `repos` is read by the approve hook (snapshot into APPROVED) and so drives the write guard. `files` is read by `devtask.py` and `diffstat.py`; **no hook enforces it**, so the implementer checks every edit target against it and review flags anything else as `unplanned`. Use full repo folder names; `files` entries are `<Repo>/<path>`, and a folder entry ending in `/` covers new files inside it.

The front-matter must be the first thing in the file. A re-plan adds `## Revision <n> (<date>)` (what changed and why) after the front-matter, before `# Change plan`. §9 lists each item as `<decision> → OPEN` or `<decision> → <user's answer>`. A plan with an OPEN item is never offered for approval, and implement refuses it.

```markdown
---
generated_by: nt-dev-coding/change-planner
generated_at: <ISO>
task_id: <id>
kind: task | bug
repos: [Ashoka-World-Backend, Nadi-Tarangini-App]
files:
  - Ashoka-World-Backend/app/Http/Controllers/EnachController.php
  - Ashoka-World-Backend/database/migrations/
  - Nadi-Tarangini-App/lib/screens/enach/enach_bloc.dart
sources:
  - repo: Ashoka-World-Backend
    commit: <HEAD sha when planned>
spec_level: impact | analysis
---

# Change plan: <title>

## 1. Summary
## 2. Spec sources        (docs-relative path, generated_at, graph_stale; confidence high|medium|low)
## 3. Changes
| # | Repo | File (lines) | Function / widget | Change | Why (AC) |
## 4. DB impact           (tables/columns read or written, new migration yes/no, data backfill, connection; "none" if none)
## 5. API contract & consumers   (changed routes/response keys; every web/app screen that calls them, from api-links)
## 6. Risks & knock-on effects   (P1/P2/P3, with what to verify)
## 7. Checks              (exact commands implement will run)
## 8. Estimate            (person-days per discipline: backend/web/app/QA, range, contingency %)
## 9. Needs your decision (new dependency, ambiguous behaviour, anything the user must answer before approving)
## 10. Out of scope
```

## implement.md, review.md, handoff.md

- **implement.md**: per change row of plan §3: status (done / skipped / blocked), file:line after the edit, one-line note. A **Deviations** section (anything not exactly as planned, with reason) and a **Checks** section (command → exit code → first relevant output lines). Resume and fix rounds append `## Round <n>: <mode> (<date>)` sections; nothing earlier is rewritten.
- **diff.md**: written only by the review skill (`diffstat.py <id>`); other skills use `diffstat.py <id> --json`, which writes nothing. `diff_sha256` identifies the change.
- **review.md**: see `agents/code-reviewer.md`. Verdict is one of `APPROVE`, `APPROVE WITH RISKS`, `CHANGES REQUIRED`. The review skill adds `reviewed_diff_sha256` (the `diff_sha256` it reviewed) to the front-matter; handoff compares it with a fresh `--json` run.
- **handoff.md**: see the `handoff` skill. Its test plan uses the nt-qa-testing `cases.md` case format so `/nt-qa-testing:plan nt-docs/dev/<id>/handoff.md` can pick it up.

## Severity

| Level | Meaning |
|---|---|
| P1 | Wrong behaviour, data loss/corruption, security hole, crash, broken consumer. Must fix before the user commits. |
| P2 | Likely problem in an edge case or a missing acceptance criterion. Should fix. |
| P3 | Risk to verify in QA on staging; no code change required. |

Cosmetic issues (naming, formatting, comments, style preferences) are never reported.
