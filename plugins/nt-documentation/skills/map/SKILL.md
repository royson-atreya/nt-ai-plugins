---
name: map
description: This skill should be used when the user asks to "map the backend", "build a module map", "map the NT app", "map the web frontend", "what modules does <repo> have", "map all repos", or runs /nt-documentation:map. Builds a module map of one Nadi Tarangini repo (or all three) from its graphify graph, starting as a draft that the user confirms.
argument-hint: <backend|web|app|all> [confirm]
allowed-tools: Bash(python3:*), Bash(git -C:*), Read, Glob, Grep, Write, Edit, Agent, SendMessage, AskUserQuestion
---

# map: module map of an NT repo

Build `$NT_DOCS_DIR/<repo-name>/module-map.json`, with `module-map.md` generated from it, for one repo. `analyze`, `diagram`, `impact` and the later plugins all depend on this map, so it is approved by the user before it counts as verified.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` first (paths, rules, freshness stamp). The JSON schema is in `${CLAUDE_PLUGIN_ROOT}/references/module-map-schema.md`.

Scripts (all read-only against the repos):

```bash
S="${CLAUDE_PLUGIN_ROOT}/scripts"
python3 "$S/graph_query.py" stamp <repo>
python3 "$S/graph_query.py" summary <repo> --depth 4
python3 "$S/laravel_routes.py" <backend|web> --by-controller
python3 "$S/module_map.py" check <repo>
python3 "$S/module_map.py" render <repo>
python3 "$S/module_map.py" confirm <repo>
python3 "$S/module_map.py" index
```

`<repo>` in script arguments is an alias (`backend`, `web`, `app`). In output paths it is the full repo directory name (see conventions.md).

## Arguments

- `backend`, `web`, `app`, or a repo directory name: map one repo.
- `all`: map all three repos, running three `module-mapper` agents in parallel.
- `<repo> confirm`: skip mapping and run the approval step (step 5) on an existing draft. Use this after hand-editing the JSON.
- No argument: ask which repo to map.

## Workflow

### 1. Stamp and check for an existing map

Run `graph_query.py stamp <repo>` (for `all`, run it for each repo and list every stale graph in a single question). If `graph_stale` is true, tell the user that the graph is behind HEAD and recommend running `graphify update .` in that repo before mapping. Continue only if the user agrees to map against the stale graph.

If `$NT_DOCS_DIR/<repo-name>/module-map.json` exists, read only its top-level fields and module ids. When it is `confirmed`, tell the user that re-mapping keeps the confirmed ids and names, and ask whether to re-map or stop.

### 2. Delegate to module-mapper

Start the `module-mapper` agent (subagent_type `nt-documentation:module-mapper`) once per repo. For `all`, send all three Agent calls in a single message so they run in parallel. Give each agent:

- the repo alias and full repo name
- `plugin_root` and `docs_dir` first (see conventions.md)
- the output path `$NT_DOCS_DIR/<repo-name>/module-map.json` (full repo name, e.g. `Ashoka-World-Backend`)
- the stamp JSON from step 1
- the path of the existing map, if any, with the instruction to keep confirmed ids
- for `web` and `app`: the fixed `product_area` list from `${CLAUDE_PLUGIN_ROOT}/references/module-map-schema.md`, so tags line up across repos even when all three run in parallel

The agent writes the JSON with `status: "draft"` and returns a short summary. Do not repeat its graph exploration in the main context.

### 3. Verify

Run `module_map.py check <repo>`. If it reports errors, or any unassigned files, send the output back to the same agent with SendMessage and ask it to fix the map, putting leftovers in `shared-*` or `infra-*` modules. If SendMessage is unavailable, start a new `module-mapper` with the check output and the existing JSON path. Allow at most two fix rounds. After that, report the remaining gaps to the user. Coverage of at least 95% with no errors is acceptable to show for approval.

### 4. Render

Run `module_map.py render <repo>`. For `all`, or when other repo maps already exist, also run `module_map.py index` to refresh `$NT_DOCS_DIR/module-index.md`.

### 5. Ask for approval

Show the user a compact table of `id | name | area | kind | files | inferred`, taking counts from the check output. List every `inferred: true` module first, with its one-line reason from `notes`. Then ask with AskUserQuestion:

- **Approve**: run `module_map.py confirm <repo>`, which re-runs check and refuses if it fails.
- **Request changes**: collect the renames, merges, splits and moves. Apply them to the JSON yourself for small edits, or send them to the agent for larger regrouping. Then repeat steps 3–5.
- **Keep as draft**: stop. Tell the user that `analyze` will warn while the map is a draft.

### 6. Report

Finish with the output paths, the module count, coverage, the status (draft or confirmed), and any stale-graph warning. Suggest `/nt-documentation:analyze <repo> <module-id>` as the next step.

## Rules specific to map

- Never read `graph.json` with Read. Use the scripts.
- Do not edit `module-map.md`. Edit the JSON and re-render.
- Never rename a confirmed module id on your own initiative. Propose it to the user and apply it only on approval, because docs and diagrams use ids as file names.
- Mark modules listed in `${CLAUDE_PLUGIN_ROOT}/references/not-in-use.md` with `status: "not-in-use"` instead of leaving them out. The research dashboard stays a single `not-in-use` module, with a note that it is an external link.
