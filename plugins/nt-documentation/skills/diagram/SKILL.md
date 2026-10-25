---
name: diagram
description: This skill should be used when the user asks to "draw a diagram", "make a draw.io diagram", "diagram the system", "high-level block diagram", "diagram the <module> module", "drill down into <module>", "update the diagram", or runs /nt-documentation:diagram. Writes stamped .drawio files for the whole Nadi Tarangini system or for one module (an overview page plus one page per flow), then has diagram-checker verify them against the code.
argument-hint: <system | [backend|web|app] <module-id>> [--no-flows]
allowed-tools: Bash(python3:*), Read, Write, Edit, Agent, AskUserQuestion
---

# diagram: draw.io diagrams (system and per module)

Write draw.io XML files to `$NT_DOCS_DIR/diagrams/`. Never hand-write mxGraph XML. Generate a JSON spec, then render it with `${CLAUDE_PLUGIN_ROOT}/scripts/drawio_build.py`, which validates the spec, applies one consistent style, embeds the source path in every box, and stamps every page with the repo commit SHAs.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` first. Draw the high-level system diagram first, then module drill-downs.

```bash
B="${CLAUDE_PLUGIN_ROOT}/scripts/drawio_build.py"
python3 "$B" spec-system --out <spec>                 # generated system spec
python3 "$B" spec-module <repo> <module-id> --out <spec>   # generated module overview page
python3 "$B" build <spec> <out.drawio>                # render (fails on an invalid spec)
python3 "$B" inspect <out.drawio>                     # list nodes and edges with sources
```

## Arguments

- `system`: the high-level block diagram, written to `diagrams/system.drawio` with its spec at `diagrams/system.spec.json`.
- `[repo] <module-id>`: the drill-down for one module, written to `diagrams/<alias>/<module-id>.drawio` (alias = `backend`, `web` or `app`) with its spec alongside. Without a repo, look the id up in all three module maps. Use the only match, and ask if several repos have it.
- `--no-flows`: write the overview page only.

## Workflow

### 1. Preconditions

- System diagram: it needs `api-links/api-links.json` and the backend `module-map.json`. If either is missing, offer to run `link-apis` or `map backend` first.
- Module diagram: it needs the repo's module map and `api-links.json`. Flow pages also need `$NT_DOCS_DIR/<repo-name>/modules/<id>.md` (full repo name). If that doc is missing, ask whether to run `/nt-documentation:analyze <repo> <id>` first or build the overview page only.
- Run `graph_query.py stamp` for every repo involved, and warn if any graph is stale or a map is still a draft. Diagrams built on a draft map get the label "draft" in their title.

### 2. Generate the spec

- **System:** `spec-system`. Check that the result reads well: no area should show 0 routes, and client edges should carry counts. Merge or rename nodes in the spec only to fix obvious noise, such as an `Unmapped` area with a few routes. Never invent edges.
- **Module overview:** `spec-module <repo> <id>`. **On a re-run, when the spec already exists:** write `spec-module` output to a temporary file, replace only the page named `Overview` in the existing spec, and keep every hand-written flow page.
- **Flow pages:** for each flow written in full in section 1.4 of the analyze doc (not the ones in its "summary only" list), append a page to the spec following `references/flow-pages.md` (in this skill folder). Take the steps, APIs, tables and business-rule ids from the analyze doc, and copy its `path:line` citations into `source`.
- If the title should say draft, prefix the spec `title` with `DRAFT: `.

### 3. Build

Run `build`. If validation fails, fix the spec and rebuild. Keep the `.spec.json` next to the `.drawio` file, because diagram-checker reads both and later re-runs start from it.

### 4. Check (automatic)

Start the `diagram-checker` agent (subagent_type `nt-documentation:diagram-checker`) in a **fresh context**. Pass `plugin_root` and `docs_dir`, then only the `.drawio` path, the `.spec.json` path, the repo names, and the output path: `<name>.check.md` next to the `.drawio`, with the same base name. Do not pass your own reasoning, the analyze doc's conclusions, or what you expect to be correct; the checker must judge from the code.

### 5. Act on the report

Read the Verdict at the top of `<name>.check.md`.

- **PASS:** report success.
- **PASS WITH NOTES or FAIL:** show the user the Wrong and Missing lists (wrong source, missing route or table, nonexistent edge, unused feature shown as live, stale stamp) and ask with AskUserQuestion whether to regenerate with fixes. On yes, apply the fixes to the spec, rebuild, and re-run the checker once.

### 6. Report

Give the file paths, page names, node and edge counts, the checker verdict, and how to open the file: draw.io desktop, app.diagrams.net (File → Open from device), or the VS Code draw.io extension. Suggest the next module to drill into: the largest confirmed module without a diagram.

## Rules specific to diagram

- Each page must carry the stamp node (`nt-stamp`). The builder adds it. Never remove it.
- Draw `not-in-use` modules and features with `status: "not-in-use"` (faded and dashed). Never draw them as live.
- External systems use the names in `${CLAUDE_PLUGIN_ROOT}/references/external-systems.md`.
- No personal or health data in labels.

## Additional resources

- **`references/flow-pages.md`**: the flow page shape, an example and rules
- `${CLAUDE_PLUGIN_ROOT}/scripts/drawio_build.py --help`: the spec format and node kinds
