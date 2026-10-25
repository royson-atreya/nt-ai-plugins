# nt-dev-coding

Implements **one approved** Nadi Tarangini task or bug at a time in `~/atreya-ai/repos` (Ashoka-World-Backend: Laravel 10 API, Nadi-Tarangini-Frontend: Laravel 8 + Blade, Nadi-Tarangini-App: Flutter/BLoC). Plans come from the specs `nt-documentation` writes to `~/atreya-ai/nt-docs`. **You do all git actions**; the plugin never commits, pushes, pulls or switches branches.

## Install

```
/plugin marketplace add ~/atreya-ai/nt-ai-plugins
/plugin install nt-dev-coding@nt-ai-plugins
```

For local development: `claude --plugin-dir plugins/nt-dev-coding`. Works alongside nt-documentation (≥ 0.1.2) and nt-qa-testing (≥ 0.1.1); older versions of those block every repo edit.

## Commands

| Command | What it does |
|---|---|
| `/nt-dev-coding:task <requirement>` | Ticket (title, requirement, description, acceptance criteria) + change plan (repos, files, functions, DB impact, API consumers, risks, estimate) → `ticket.md`, `plan.md`. Stops for approval. |
| `/nt-dev-coding:bug <report>` | Same, from reproduction steps, with the suspected root cause as `file:line` → `bug.md`, `ticket.md`, `plan.md`. Stops for approval. |
| `approve <id>` / `revoke <id>` | **Typed by you** as the whole prompt. A hook records the approval; nothing else can. |
| `/nt-dev-coding:implement <id> [fix R-01 …]` | Surgical edits on your feature branch, then `php -l` / `flutter analyze --no-pub` / `dart format --output=none` → `implement.md` |
| `/nt-dev-coding:review [id]` | `diff.md` (every +/- line by file, counts, unplanned/pre-existing flags) and an independent read-only review → `review.md` |
| `/nt-dev-coding:handoff [id]` | Summary, files with +/-, review result, commit message per repo, deploy notes, staging retest plan in nt-qa-testing format → `handoff.md` |

Typical flow: `task` → read plan → `approve <id>` → `git -C <repo> checkout -b feature/<id>` (you) → `implement` → `review` → (fix round) → `handoff` → you commit, push, deploy to staging → `/nt-qa-testing:plan nt-docs/dev/<id>/handoff.md`.

If no impact report or module analysis covers the area, `task`/`bug` stop and suggest `/nt-documentation:impact "<change>"`.

## Output

```
~/atreya-ai/nt-docs/dev/
  ACTIVE                       # active task id (hook-written)
  <id>/ bug.md ticket.md plan.md APPROVED base.json implement.md diff.md review.md handoff.md
```

## Safety (hooks)

| Hook | Rule |
|---|---|
| UserPromptSubmit `approve.py` | `approve <id>` writes `APPROVED` (repos from plan.md front-matter + plan sha256) and `ACTIVE`; `revoke <id>` removes them. |
| PreToolUse `guard.py` | Write/Edit in the repos only if the active task is approved, plan.md is unchanged since approval, the repo is in the plan and its branch is not master/main/production. Write creates new files only (existing files: Edit). HEAD must name an existing branch. Bash writes into the repos are refused: redirects (incl. `3>`, `&>`, `>|`), rm/mv/cp/`cp -t`/dd/tee/..., in-place sed/perl (`-i`, `-Ei`, `-pi`), `find -delete`/`-exec` (only grep/wc/ls/stat/file), `xargs` (same), curl/wget output, archive extraction, and inline interpreter code (`python -c`, `node -e`, heredocs) aimed at the repos. Claude cannot write `APPROVED`/`ACTIVE`. The guard fails closed: a crash or a missing `devgate.py` blocks the call. |
| | git is allowlisted in the workspace: status, diff, log, show, blame, rev-parse, ls-files and similar reads, plus listing forms of branch/tag/stash/remote/config/symbolic-ref. Everything else (commit, push, pull, checkout, switch, merge, rebase, reset, stash, tag, add, restore, fetch, config writes, symbolic-ref, remote add, ...) is refused, as are `git -c`, `GIT_*` env overrides and `--output`/`--ext-diff`. |
| | `php artisan` only route:list, list, about, --version (the backend `.env` points at **production**); `php` only `-l`/`-v`; no phpunit/pest/sail. Note: `route:list` and `about` boot the app with that `.env`. |
| | composer/npm/yarn/pnpm/pod: read-only subcommands only; no npx; flutter only `analyze --no-pub`, `--version`, `doctor`, `devices`; dart only `format --output=none`, `analyze`, `info`. |
| | Never read `.env*`, `*.jks`, `*.keystore`, `firebase-*.json`, `google-services.json`, `GoogleService-Info.plist` (Read, Grep, Glob, Bash). |
| SessionStart `session_banner.py` | Lists the commands and the active task with each repo's branch. |

`hooks/devgate.py` is the shared repo-write rule; identical copies live in nt-documentation and nt-qa-testing so all three guards agree. Edit it here and copy it over (the tests check the copies match).

Limits: the hooks catch direct tool calls and the common shell forms above, not every possible program (a script file written elsewhere and then run could still write a file; a hook that times out does not block). The write gate is per repo, not per file: unplanned files in an approved repo are caught afterwards by `diff.md` and review. They are a strong safety net, not a sandbox.

## Prerequisites

- `python3` (3.9+), `git`; `php` for PHP checks; `flutter`/`dart` for app checks (missing tools are reported as "not run").
- nt-documentation specs (module maps, analyses, api-links, impact) under `~/atreya-ai/nt-docs`.

## Tests

```
bash tests/test_guard.sh     # hooks: approval, write gate, git/artisan/package/secret rules, banner
bash tests/test_scripts.sh   # devtask.py and diffstat.py on fixture repos
```

Both build throwaway repos in a temp dir and never touch `~/atreya-ai/repos`.
