# nt-documentation conventions

Every skill and agent in this plugin follows these rules. Read this file before doing any work.

## Paths

| What | Default | Override |
|---|---|---|
| Product repos (read-only) | `~/atreya-ai/repos` | `NT_REPOS_DIR` |
| Output (docs and diagrams) | `~/atreya-ai/nt-docs` | `NT_DOCS_DIR` |

Repos and their short aliases (accepted by `graph_query.py`):

| Alias | Repo | Stack | How it reaches the backend |
|---|---|---|---|
| `backend` | Ashoka-World-Backend | Laravel 10 API, MySQL (`mysql`, `turyaa_db`, `samvit_chakra_db` connections) | serves `routes/api.php` (~1000 `Route::` lines) and `routes/web.php` |
| `web` | Nadi-Tarangini-Frontend | Laravel 8 + Blade | `config('app.backend_url') . '/endpoint'` (env `BACKEND_URL`) |
| `app` | Nadi-Tarangini-App | Flutter + BLoC, code in `lib/` | `FlavorConfig.baseUrl + endpoint` (`lib/common_files/utilities/flavor_config.dart`); BLE via `flutter_blue_plus` |

## Script shorthand and agent hand-off

- In skills and agents, `graph_query.py stamp backend` (any bare `<script>.py`) is shorthand for `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py" ...`.
- When a skill starts an agent, the agent prompt **always** begins with `plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>` and `docs_dir=<expanded $NT_DOCS_DIR, default ~/atreya-ai/nt-docs>`, followed by the task inputs. Agents may not see `${CLAUDE_PLUGIN_ROOT}` expanded.

## Hard rules

1. **Never modify the product repos.** Read-only git is fine (`log`, `show`, `rev-parse`, `blame`, `diff`). A hook enforces this.
2. **Never read secrets**: `.env*`, `*.jks`, `*.keystore`, `firebase-*.json`, `google-services.json`, `GoogleService-Info.plist`. Config files such as `config/services.php` may be read for **key names only**. Never copy values, URLs with tokens, or credentials into docs.
3. **No patient data.** Do not query databases, do not copy seed/fixture rows, logs, or sample payloads containing names, phone numbers, emails, health readings, or report contents. Describe *fields*, not *values*.
4. **Never write product code, tests, or UI.** Output is documentation, diagrams, and plans only.
5. **Write only under the output dir** (`$NT_DOCS_DIR`).
6. **Use graphify first.** Each repo has `graphify-out/graph.json` (1–10 MB — never Read it directly) and `graphify-out/GRAPH_REPORT.md`. Query the graph with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/graph_query.py"`. Open source files only to confirm specific facts the graph cannot give (route definitions, `$table`, validation rules, business logic).
7. **One module at a time.** Never try to explain a whole repo in one pass.
8. **Cite evidence.** Every claim in a doc points to `path:line` or a graph query. Mark anything inferred as `(inferred)` and anything unconfirmed as `TODO: verify`.
9. **Respect `references/not-in-use.md`.** Mention unused features as unused; do not document them as live behaviour.

## Freshness stamp

Every output file starts with a stamp produced by:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/graph_query.py" stamp <repo>   # one per repo involved
```

Markdown front-matter form:

```yaml
---
generated_by: nt-documentation/<skill>
generated_at: <ISO date>
sources:
  - repo: Ashoka-World-Backend
    commit: <full sha>
    graph_commit: <graphify built_at_commit>
    graph_stale: false
---
```

If `graph_stale` is true, say so at the top of the doc and suggest `graphify update .` in that repo (the user runs it; do not run it yourself).

draw.io files carry the same information in a stamp text box (see the `diagram` skill).

## Output layout

```
$NT_DOCS_DIR/
├── <repo>/module-map.md            # map
├── <repo>/module-map.json          # map (machine-readable, used by other skills/plugins)
├── <repo>/modules/<module>.md      # analyze (includes the functional spec)
├── api-links/api-links.json|csv|md # link-apis
├── diagrams/system.drawio          # diagram system
├── diagrams/<alias>/<module>.drawio # diagram <module> (+ .spec.json)
├── diagrams/**/<name>.check.md     # diagram-checker report
├── impact/<date>-<slug>.md         # impact
└── sprint-plans/<date>-<slug>.md   # plan-sprint
```

`<repo>` in output paths is **always the full repo directory name** (`Ashoka-World-Backend`, `Nadi-Tarangini-Frontend`, `Nadi-Tarangini-App`), never the alias. Aliases (`backend`, `web`, `app`) are only for script arguments and skill arguments. Exception: the diagrams folder uses the alias (`diagrams/backend/<id>.drawio`).

Module ids are kebab-case (`nadi-pariksha`, `medical-inventory`). Elsewhere in docs, a module is referred to as `<alias>:<module-id>` (e.g. `backend:medical-inventory`).

Plugin-level reference files are always referred to as `${CLAUDE_PLUGIN_ROOT}/references/<file>`. A bare `references/<file>` inside a skill means that skill's own `references/` folder.

## Downstream consumers

`nt-qa-testing` and `nt-dev-coding` will read these files as verified context. Keep them factual, stamped, and evidence-linked; prefer tables over prose; keep the JSON outputs schema-stable.
