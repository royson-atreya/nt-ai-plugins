# nt-documentation

A read-only plugin that explains the Nadi Tarangini (NT) codebases. It produces module maps, per-module functional specs, cross-repo API links, draw.io diagrams and change-impact analysis, and can turn an approved change into Zoho Sprints tasks. It is the first plugin in the `nt-ai-plugins` marketplace. `nt-qa-testing` and `nt-dev-coding` will use its output as verified context.

**It never writes product code, tests or UI, never modifies the product repos, and never handles patient data or secrets.**

## Prerequisites

- The three repos at `~/atreya-ai/repos/` (override with `NT_REPOS_DIR`): `Ashoka-World-Backend`, `Nadi-Tarangini-Frontend`, `Nadi-Tarangini-App`
- A graphify graph in each repo (`graphify-out/graph.json`). Run `graphify update .` in a repo after it changes. The plugin never runs graphify itself.
- `python3` (3.9+, standard library only). `jq` is optional.
- Output goes to `~/atreya-ai/nt-docs/` (override with `NT_DOCS_DIR`).
- Optional: the Zoho Sprints connector for `plan-sprint`.

## Install

```
/plugin marketplace add ~/atreya-ai/nt-ai-plugins
/plugin install nt-documentation@nt-ai-plugins
```

For local development: `claude --plugin-dir plugins/nt-documentation`.

## Commands (in the recommended order)

| Command | What it does | Output |
|---|---|---|
| `/nt-documentation:map <backend\|web\|app\|all>` | Module map from graphify, starting as a draft that you confirm | `<repo>/module-map.json`, `.md`, `module-index.md` |
| `/nt-documentation:link-apis` | Screen → API → route → controller → tables across the 3 repos | `api-links/api-links.{json,csv,md}`, `overrides.json`, `api-links-review.md` |
| `/nt-documentation:analyze <repo> <module-id> [--focus x]` | One module: functional spec plus technical reference | `<repo>/modules/<id>.md` |
| `/nt-documentation:diagram system` / `<repo> <module-id>` | Stamped draw.io files, checked automatically against the code | `diagrams/system.drawio`, `diagrams/<repo>/<id>.drawio`, `*.check.md` |
| `/nt-documentation:impact <change request>` | Affected modules, screens, APIs and tables, plus a person-day estimate and work items | `impact/<date>-<slug>.md` |
| `/nt-documentation:plan-sprint <impact report>` | After your approval: Epic + Stories + Tasks in the Zoho P7 backlog, or a task-list file | `sprint-plans/…`, Zoho ids recorded in the report |

Run `map` first. Everything else is more accurate once the maps are **confirmed**.

## Agents

| Agent | Model | Used by | Role |
|---|---|---|---|
| `module-mapper` | opus | map | Groups a repo into stable modules |
| `module-analyst` | sonnet | analyze | Writes one module's spec and reference |
| `api-linker` | sonnet | link-apis | Resolves dynamic calls (overrides), verifies samples, classifies orphan routes |
| `diagram-checker` | sonnet | diagram | Checks diagrams against the code in a fresh context; reports only |

## Hooks

- **SessionStart:** a banner listing the commands and any stale graphs (only when the session starts under `~/atreya-ai`).
- **PreToolUse guard** (`hooks/guard.py`, deterministic, fails closed on unexpected input, tested by `tests/test_guard.sh`). It acts **only on Nadi Tarangini paths**: anything inside a git repo whose `origin` is `github.com/Atreya-Innovations/*` (https or ssh), or under `~/atreya-ai` (override with `NT_WORKSPACE`). Other projects are untouched.
  - Blocks reading `.env*`, `*.jks`, `*.keystore`, `firebase-*.json`, `google-services.json` and `GoogleService-Info.plist` in those paths, including through Bash.
  - Treats product repos as read-only: Atreya-origin repos and anything under `NT_REPOS_DIR`, except `nt-docs` and repos with `.claude-plugin/marketplace.json` at the root (such as this marketplace). It blocks Write/Edit and modifying Bash commands there (git writes, rm, mv, cp into, redirects, `sed -i`, graphify).
  - Inside the repos, searches must be limited to code types (`Grep type=php`, `grep -r --include='*.php'`, `rg -t dart`). Several secret files are committed to these repos, so an unrestricted search could print them.
  - Inside the repos, `git show`/`diff`/`log -p` need a code-file pathspec or `--stat`.
  - Blocks writing secret-looking strings (API keys, tokens, private keys) into `nt-docs`.
- **PreToolUse Zoho:** asks you before any Zoho call that is not a Get/List/Search.

## Scripts (`scripts/`, read-only and standard library only)

| Script | Purpose |
|---|---|
| `graph_query.py` | Compact graphify queries: stamp, summary, folder, file, search, neighbors |
| `laravel_routes.py` | Static route parser (verified: backend 915, web 400 routes) |
| `laravel_data.py` | Models → tables → DB connections, and which files touch which tables |
| `module_map.py` | Check, render, confirm and index module maps, and find which module owns a file |
| `link_apis.py` | The cross-repo trace (applies `overrides.json`) |
| `drawio_build.py` | Generates system and module specs, renders `.drawio`, inspects diagrams |
| `impact_seed.py` | Deterministic starting point for impact analysis, including knock-on expansion |
| `work_items.py` | Validates and totals work items, task-list fallback |

## References (`references/`)

- `conventions.md`: paths, hard rules, the freshness stamp, the output layout
- `external-systems.md`: Lambda/API Gateway, S3, Samvit Chakra, Interakt, ZeptoMail, Razorpay, ENACH, the extra DBs, the BLE device
- `not-in-use.md`: Receptionist, the research dashboard, TestPurpose
- `domain-glossary.md`: **a stub for the NT team to fill in** (nadi, dosha, Turyaa, Guna and other terms)
- `module-map-schema.md`, `work-items-schema.md`: the data contracts other plugins rely on

## Known limits (v1)

- Static analysis only. Dynamic URLs need `api-links/overrides.json`, which api-linker maintains.
- Table level `file` in api-links is an upper bound: the controller file's tables.
- No memory and no evals yet. Each run re-reads the current docs.
- The Bash guard is pattern-based. It covers the common read and write forms, but it is not a sandbox: string tricks such as `python3 -c "open('.e'+'nv')"` get past it.
- `plan-sprint`'s `allowed-tools` name this account's Zoho connector (`claude_ai_Zoho_MCP_Atreya`).
