---
name: analyze
description: This skill should be used when the user asks to "analyze a module", "explain the NadiPariksha module", "how does ENACH work", "write the functional spec for <module>", "document <module> in the app/web/backend", or runs /nt-documentation:analyze. Explains ONE module of one Nadi Tarangini repo, producing a functional spec plus a technical reference, never the whole repo at once.
argument-hint: <backend|web|app> <module-id> [--focus <controller|flow>]
allowed-tools: Bash(python3:*), Bash(git -C:*), Bash(jq:*), Read, Glob, Grep, Write, Edit, Agent, SendMessage, AskUserQuestion
---

# analyze: explain one module

Write `$NT_DOCS_DIR/<repo-name>/modules/<module-id>.md`, where `<repo-name>` is the full repo directory name (`Ashoka-World-Backend`, …). Part 1 is a plain-language functional spec for product and QA. Part 2 is a technical reference for developers. Both cite code. QA and dev plugins will rely on this doc, so accuracy beats coverage.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` first. The doc layout is in `references/module-doc-template.md` (in this skill folder).

## Arguments

- `<repo>`: `backend`, `web` or `app`.
- `<module-id>`: an id from `$NT_DOCS_DIR/<repo-name>/module-map.json`.
- `--focus <controller|flow>` (optional): deep-dive one controller or flow of a large module and merge the result into the existing doc instead of rewriting it. If the doc does not exist yet, run a full analysis first. Never write a focus-only doc.
- If the module id is missing or unknown, list the map's module ids with their summaries and ask which one to analyze. Never fall back to analyzing the whole repo.

## Workflow

### 1. Preconditions

1. Load the module map. If it is missing, stop and suggest `/nt-documentation:map <repo>`.
2. If the map is `draft`, warn the user that the module boundaries are unconfirmed. Continue only if the user accepts, and record `module_map_status: draft` in the doc.
3. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/graph_query.py" stamp <repo>`. If the map's `commit` differs from HEAD, say the map may be outdated.
4. If the module is `not-in-use`, ask whether to document it anyway. If yes, keep the doc short and mark it unused at the top.
5. If the doc already exists, read its front matter. With the same commit and no `--focus`, ask whether to regenerate or stop.
6. Size the module: run `module_map.py check <repo>` and read this module's file count from "files per module". Take the route count from the module's `route_count` in the map.

### 2. Delegate to module-analyst

Start the `module-analyst` agent (subagent_type `nt-documentation:module-analyst`). Its prompt begins with `plugin_root` and `docs_dir` (see conventions.md), then:

- the repo, the module JSON object copied from the map, and the stamp
- the output path, plus the template path `${CLAUDE_PLUGIN_ROOT}/skills/analyze/references/module-doc-template.md`
- the `--focus` target, if any. In focus mode, the agent updates only the matching flow, API rows and rules in the existing doc.
- whether `$NT_DOCS_DIR/api-links/api-links.json` exists (for section 2.5)

For large modules (more than about 40 routes, or more than about 80 files, from step 1.6), tell the agent to list every route in 2.1 but deep-dive only the 5–8 most important flows, chosen by route count, graph centrality and the summary in the map.

### 3. Spot-check

When the agent returns, check the doc yourself before reporting it:

- The front-matter stamp matches the stamp from step 1.
- Every section of the template is present.
- Pick three `path:line` citations at random and open those lines to confirm they say what the doc claims. If any are wrong, send the problems back to the agent with SendMessage for one fix round. If SendMessage is unavailable, start a new module-analyst with the doc path and the list of problems (fix-round mode).
- Search the doc for anything that looks like real personal or health data: phone numbers, emails, names attached to readings, or sample payloads with values. If found, remove it with Edit.

### 4. Report

Reply with:

- the doc path
- counts: features, flows (deep / summary), APIs, business rules, tables, open questions
- the top three open questions
- next steps: `/nt-documentation:diagram <repo-alias> <module-id>` to draw it, and `/nt-documentation:analyze <repo> <module-id> --focus <x>` for a deeper look at a summary-only flow

## Rules specific to analyze

- One module per run. Never loop over every module unprompted. If asked to analyze "everything", propose an order (confirmed modules first, largest first) and run one module at a time with user confirmation between runs.
- Describe data by **fields and shapes**, never by values. Do not copy seeders, fixtures, logs or sample JSON with real-looking values.
- Requests and responses come from code (FormRequest, `$request->validate`, `response()->json` shapes, Dart model classes), not from guesses. Write `TODO: verify` where the code does not show the answer.

## Additional resources

- **`references/module-doc-template.md`**: the full section layout, with table formats
- `${CLAUDE_PLUGIN_ROOT}/scripts/laravel_data.py`: which tables a module touches (`uses <path>`), and model metadata
- `${CLAUDE_PLUGIN_ROOT}/scripts/laravel_routes.py`: a module's routes (`--grep <prefix|Controller>`)
