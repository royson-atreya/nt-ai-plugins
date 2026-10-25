---
name: link-apis
description: This skill should be used when the user asks to "link the APIs", "which screens call this API", "map screens to backend routes", "trace screen to table", "which tables does this screen touch", "find unused backend routes", or runs /nt-documentation:link-apis. Builds the cross-repo trace web/mobile screen → API call → backend route → controller → DB table for all three Nadi Tarangini repos.
argument-hint: "[--review] [<uri|screen|table> to query]"
allowed-tools: Bash(python3:*), Bash(jq:*), Read, Glob, Grep, Write, Agent, AskUserQuestion
---

# link-apis: screen → API → route → controller → table

Build `$NT_DOCS_DIR/api-links/` (`api-links.json`, `api-links.csv`, `api-links.md`) with the deterministic script `${CLAUDE_PLUGIN_ROOT}/scripts/link_apis.py`, then have the `api-linker` agent resolve the calls the script cannot resolve on its own. `analyze` (section 2.5), `diagram` and `impact` all read `api-links.json`.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` first.

## Arguments

- No argument: full run (steps 1–5).
- `--review`: requires an existing `api-links.json`. Skip step 2 and run steps 3–5 (the agent, then re-run the script).
- A query (a URI like `/v2/report/getCurrentVisitInputForDiet`, a screen file name, or a table name): answer from the existing `api-links.json` with `jq` or `python3 -c`, without regenerating. If the file is missing, or any `sources[].commit` differs from the current `graph_query.py stamp` commit of that repo, offer a full run first.

## Workflow

### 1. Freshness

Run `graph_query.py stamp` for `backend`, `web` and `app`. Warn about any stale graph. The script itself parses source files, so a stale graph mostly affects module ownership, not the links.

Note whether module maps exist for the three repos. Without them the `*_module` fields stay empty. Suggest running `/nt-documentation:map` first, but do not block on it.

### 2. Run the script

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/link_apis.py"
```

It prints a JSON summary: client calls, linked, unmatched, orphan routes, match kinds, and method mismatches. It applies `$NT_DOCS_DIR/api-links/overrides.json` if that file exists. **Keep this first summary**, because step 4 compares against it.

### 3. Review with api-linker

Start the `api-linker` agent (subagent_type `nt-documentation:api-linker`) when there are unmatched client calls, method mismatches, `case-mismatch` matches, or more than 10 links with no screens (`jq '[.links[]|select(.screens==[])]|length' "$NT_DOCS_DIR/api-links/api-links.json"`). Give it `plugin_root` and `docs_dir` first (see conventions.md), then the output folder and the summary. It will:

- resolve unmatched and dynamic calls by reading the client code, then append entries to `overrides.json`
- spot-check about 10 random links end to end against the code
- classify orphan backend routes (other client such as the Ashoka dashboard or the Turyaa app, partner or public API, cron or webhook, test, or probably dead)
- write `api-links-review.md` with its findings

After the agent finishes, re-run the script so the overrides take effect, and compare the summaries before and after.

### 4. Check the result

- The `unmatched_client_calls` count should drop after overrides. Anything left must have a reason in `api-links-review.md`.
- Search `api-links.md` and `api-links-review.md` for anything that looks secret-like or personal. The script strips query strings, but an agent's notes could still leak something.

### 5. Report

Reply with the summary table (linked, unmatched before and after, orphans by hint), the three most notable findings (for example a client calling an endpoint that no longer exists, or a write route with no validation), and the paths of the output files. Suggest `/nt-documentation:diagram system` next.

## Output contract (other skills rely on this)

`api-links.json` has a top-level `schema_version: 1`, `generated_at`, `sources` (stamps), `summary`, `links[]`, `unmatched_client_calls[]` and `orphan_routes[]`. Each link holds `client`, `client_module`, `screens[]`, `client_entry{file,line,symbol,via,client_routes}`, `method`, `uri`, `match` (`exact|param|case-mismatch|override`), `method_ok`, `backend{methods,uri,controller,action,controller_file,route,middleware,module}` and `tables[{table,connection,level(action|service|service-file|file),write,via?}]`. Do not change these fields without bumping `schema_version`.

## Known limits (state them in reports)

- Static analysis only. Fully dynamic URLs need overrides.
- Table level `file` means the action's own body and the services it calls showed no model use, so the tables listed are everything the controller file touches. Treat that as an upper bound.
- Web "screens" are Blade views returned by the web action, plus the Blade and JS files that reference the web route URI or name. App "screens" are files that import the BLoC or repository caller and are not themselves logic files.
