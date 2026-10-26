# nt-ai-plugins

Atreya AI's Claude Code plugin marketplace for the **Nadi Tarangini (NT)** codebases. It has three plugins that cover the path from understanding a change, to building it, to testing it on staging:

| Plugin | Version | Role | Writes to |
|---|---|---|---|
| [`nt-documentation`](plugins/nt-documentation/README.md) | 0.1.2 | Read-only understanding: module maps, functional specs, cross-repo API links, draw.io diagrams, impact analysis, Zoho sprint planning | `~/atreya-ai/nt-docs/` |
| [`nt-dev-coding`](plugins/nt-dev-coding/README.md) | 0.1.0 | Implements **one approved** task or bug: ticket + plan, user approval gate, surgical edits on your branch, diff, independent review, hand-off. **You do all git actions.** | `nt-docs/dev/<id>/`, plus the repos for the approved task only |
| [`nt-qa-testing`](plugins/nt-qa-testing/README.md) | 0.1.1 | Spec-driven QA of one task or bug on **web staging**: plan, cases, Playwright run with screenshots, evidence check, report, workbook CSV | `nt-docs/qa/<id>/` |

Each plugin's README has the full command list, output layout, hooks and limits. This page covers what they share.

## How they fit together

```
nt-documentation            nt-dev-coding                         nt-qa-testing
────────────────            ─────────────                         ─────────────
map → link-apis →           task / bug → (you) approve <id> →     plan → cases →
analyze → diagram →   ──►   (you) git checkout -b feature/<id> →  ──►  run-web → report
impact [→ plan-sprint]      implement → review → handoff →             (retest <bug-id>)
                            (you) commit, push, deploy to staging
```

1. **Understand.** `/nt-documentation:map all`, then `link-apis`, `analyze` and `impact "<change>"` for the area you are changing. These specs are the verified context the other two plugins rely on.
2. **Build.** `/nt-dev-coding:task <requirement>` (or `bug <report>`) writes a ticket and change plan and stops. Read the plan, then type `approve <id>` yourself. Create the feature branch, then run `implement`, `review` and `handoff`. You commit, push and deploy.
3. **Test.** `/nt-qa-testing:plan nt-docs/dev/<id>/handoff.md`, then `cases`, `run-web` and `report`. For bugs, `retest <bug-id>` says fixed / not fixed.

`nt-dev-coding` and `nt-qa-testing` stop and point you to `/nt-documentation:analyze` or `/nt-documentation:impact` when no spec covers the area.

## Install

```
/plugin marketplace add ~/atreya-ai/nt-ai-plugins
/plugin install nt-documentation@nt-ai-plugins
/plugin install nt-dev-coding@nt-ai-plugins
/plugin install nt-qa-testing@nt-ai-plugins
```

Install only the ones you need. If you install more than one, keep them at least at the versions in the table above. Older nt-documentation (< 0.1.2) and nt-qa-testing (< 0.1.1) guards block every repo edit nt-dev-coding makes.

`nt-qa-testing` asks for the staging URL and test accounts when it is enabled (stored in secure storage, never in this repo). Change them later with `/plugin` → Installed → nt-qa-testing → **Configure options**.

For local development, load a plugin straight from disk:

```
claude --plugin-dir plugins/<plugin-name>
```

## Prerequisites

- **Start Claude Code from `~/atreya-ai`.** The guards, banners and credential injection key off this workspace.
- `python3` 3.9+ on `PATH` (hooks and scripts, standard library only), and `git`.
- The product repos under `~/atreya-ai/repos/` (override with `NT_REPOS_DIR`):
  - `Ashoka-World-Backend`: Laravel 10 API
  - `Nadi-Tarangini-Frontend`: Laravel 8 + Blade web dashboard
  - `Nadi-Tarangini-App`: Flutter / BLoC mobile app
- A graphify graph in each repo (`graphify-out/graph.json`) for nt-documentation. Refresh it with `graphify update .` after the repo changes.
- Optional, per plugin: `php`, `flutter`/`dart` (nt-dev-coding checks), the **playwright** plugin (nt-qa-testing), the Zoho Sprints connector (`/nt-documentation:plan-sprint`).

## Workspace layout

```
~/atreya-ai/
  nt-ai-plugins/        # this marketplace
  repos/                # product repos: read-only except for an approved nt-dev-coding task
  nt-docs/              # all plugin output (override with NT_DOCS_DIR)
    module-index.md     #   index of all modules (nt-documentation)
    Ashoka-World-Backend/ Nadi-Tarangini-Frontend/ Nadi-Tarangini-App/
                        #   per repo: module-map.json/.md, modules/<id>.md
    api-links/ diagrams/ journeys/ impact/ sprint-plans/
    dev/ACTIVE          #   active nt-dev-coding task (written by a hook, never by Claude)
    dev/<id>/           #   ticket, plan, APPROVED, implement, diff, review, handoff
    qa/<id>/            #   plan, cases, screenshots, run, check, report, results.csv
```

## Shared safety model

All three plugins enforce their rules with deterministic Python hooks, not with instructions alone:

- **Secrets are never read.** `.env*`, `*.jks`, `*.keystore`, `firebase-*.json`, `google-services.json` and `GoogleService-Info.plist` are blocked through Read, Grep, Glob and Bash. Searches inside the repos must be limited to code file types, because some secret files are committed.
- **Product repos are read-only** with one exception: Write/Edit for the active nt-dev-coding task that **you** approved by typing `approve <id>`, only in a repo named in its plan, only on a branch other than `master`/`main`/`production`. Bash writes to the repos stay blocked. Claude can never write the approval markers.
- **No git writes.** Commit, push, pull, checkout and the rest are refused. Only read-only git is allowed.
- **Production is off limits.** The backend `.env` points at production, so `php artisan` is limited to a few read-only commands. QA browsing is allowed only on staging hosts.
- **External writes need confirmation.** Any Zoho call that is not a Get/List/Search asks you first.

The repo-write rule lives in `hooks/devgate.py`, and **an identical copy is kept in each plugin** so the three guards always agree. Edit it in `plugins/nt-dev-coding/hooks/devgate.py`, copy it to the other two, and run the tests (they check that the copies match).

The hooks are a strong safety net, not a sandbox. Each plugin README lists exactly what they do and do not catch.

## Repository layout

```
.claude-plugin/marketplace.json   # marketplace manifest
plugins/<plugin>/
  .claude-plugin/plugin.json      # name, version, description (and userConfig for nt-qa-testing)
  skills/<command>/SKILL.md       # one per /<plugin>:<command>, with references/ templates
  agents/*.md                     # subagents (planner, reviewer, analyst, runner, checkers…)
  hooks/hooks.json + *.py         # SessionStart banner, PreToolUse guards, etc.
  scripts/*.py                    # deterministic helpers called by the skills
  references/*.md                 # conventions, schemas, scope rules
  tests/*.sh                      # hook and script tests
  README.md
```

## Tests

Run these after changing a hook, script or `devgate.py`. They use temp directories and fake credentials, and never touch `~/atreya-ai/repos`.

```
bash plugins/nt-documentation/tests/test_guard.sh
bash plugins/nt-dev-coding/tests/test_guard.sh
bash plugins/nt-dev-coding/tests/test_scripts.sh
bash plugins/nt-qa-testing/tests/test_guard.sh
```

## Releasing a change

1. Make the change and run the tests above.
2. Bump `version` in the plugin's `.claude-plugin/plugin.json` and update its README.
3. If `devgate.py` changed, bump all three plugins and update the minimum versions in the Install section.
4. Users pick it up with `/plugin marketplace update nt-ai-plugins`.
