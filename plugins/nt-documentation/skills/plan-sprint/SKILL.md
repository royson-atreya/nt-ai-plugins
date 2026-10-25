---
name: plan-sprint
description: Turns the approved "Proposed work items" of a nt-documentation impact report into an Epic, Stories and Tasks in the Zoho Sprints P7 backlog, only after explicit user approval in the same session, or into a task-list file when no Zoho connector is available. Invoked only by the user, via /nt-documentation:plan-sprint <impact report>.
argument-hint: <path to impact report>
disable-model-invocation: true
allowed-tools: Bash(python3:*), Read, Write, AskUserQuestion, mcp__claude_ai_Zoho_MCP_Atreya__ZohoSprints_GetProjects, mcp__claude_ai_Zoho_MCP_Atreya__ZohoSprints_GetProjectDetails, mcp__claude_ai_Zoho_MCP_Atreya__ZohoSprints_GetProjectPriorities, mcp__claude_ai_Zoho_MCP_Atreya__ZohoSprints_GetItems
---

# plan-sprint: impact work items → Zoho Sprints P7

Read the work items block from an impact report (`$NT_DOCS_DIR/impact/<file>.md`). Get the user's explicit approval. Then create one Epic, plus Story and Task items in the **backlog** of Zoho Sprints project **P7**. If no Zoho connector is available, write a task-list file instead.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md`, `${CLAUDE_PLUGIN_ROOT}/references/work-items-schema.md` and `references/zoho-mapping.md` (in this skill folder) first.

Only the read-only Zoho tools are pre-approved in `allowed-tools`. The create, epic and link tools are left out on purpose, so each write goes through the normal permission prompt plus the plugin's Zoho confirmation hook.

```bash
W="${CLAUDE_PLUGIN_ROOT}/scripts/work_items.py"
python3 "$W" check <report>                 # validate + totals
python3 "$W" show <report>                  # compact story/task table for approval
python3 "$W" extract <report> > <tmp.json>  # get the JSON to edit
python3 "$W" update <report> <tmp.json>     # write it back (validated)
python3 "$W" tasklist <report> <out.md>     # fallback without Zoho
```

To change the block, always extract it, edit the JSON, Write it to `$NT_DOCS_DIR/sprint-plans/.wi-<slug>.json`, then run `update`. Never hand-edit the fenced block inside the report.

## Workflow

### 1. Load, validate and detect the target

1. If no argument was given, list `$NT_DOCS_DIR/impact/*.md`, newest first, and ask which report to use.
2. Run `work_items.py check`. On errors, stop and send the user back to `/nt-documentation:impact` to fix them.
3. **Detect the target:** check whether the Zoho Sprints tools (`mcp__*Zoho*__ZohoSprints_*`) are available in this session. The target is "Zoho Sprints P7 backlog" if they are, and "task-list file" if not.
4. **Check earlier pushes** (`extract`, then look at `zoho`):
   - `zoho` covers every story and task key and `links_done` is true: the push is complete. Show the refs and stop, unless the user asks to re-push specific stories.
   - `zoho` is partial: an earlier push was interrupted. Offer to **resume**, creating only the missing keys.
   - `task_list_file` is set: say so, and ask whether to push to Zoho now that a connector may be available.

### 2. Ask for approval (required)

Show the output of `work_items.py show`, the totals from `check`, and the target from step 1, e.g. "Zoho Sprints P7 backlog: 1 epic + 3 stories + 9 tasks" or "task-list file". When resuming, show only the missing items. Ask with AskUserQuestion:

- **Approve and create**
- **Edit first**: collect the changes, apply them through extract, edit and update, then show and ask again
- **Cancel**

Proceed only on an explicit "Approve and create" in this session. An approval from an earlier session or for a different report does not count. Then set `status: "approved"` and `approved_at` through extract, edit and update.

### 3. Fallback without Zoho

If the target is the task-list file, run `work_items.py tasklist <report> $NT_DOCS_DIR/sprint-plans/<date>-<slug>.md`, record `task_list_file` in the block, report, and stop.

### 4. Resolve the Zoho config (first run only)

If `$NT_DOCS_DIR/sprint-plans/zoho-config.json` exists, load it and show the project name for a quick confirmation. Otherwise follow "Resolving the IDs" in zoho-mapping.md: ask for the teamId, then make the read-only calls to find P7, the backlog id, the Story and Task item type ids, the priorities and a link type. Show the result and write the config only after the user confirms it.

### 5. Create the items

Follow "Creating items" in zoho-mapping.md, in order: epic, then stories, then tasks, then links. Skip every key already in `zoho`. The permission prompt and the Zoho hook ask the user before each write. If the user declines one, stop and report what was created so far.

After **each** successful create, record the returned id right away with extract, edit and update. The shape is defined in work-items-schema.md: `{"project_id", "epic_id", "stories": {"S1": id}, "tasks": {"S1-T1": id}, "links_done": false}`. Set `links_done: true` after the last link, or immediately if `linkTypeId` is null. This way a rerun never duplicates items.

On an API error, stop. Show the error and the items already created, and suggest a fix (a wrong item type id usually means deleting `zoho-config.json` and resolving again). A rerun resumes from step 1.4.

### 6. Report

List the epic, stories and tasks created with their Zoho ids, the totals, and where the refs were recorded in the impact report.

## Rules specific to plan-sprint

- Never create, update, move or delete anything in Zoho without the approval in step 2. Never touch existing Zoho items. This skill only creates new ones.
- Use only the backlog. Never start, complete or modify sprints.
- Leave `point`, `duration`, assignees and dates unset. Estimates go in the description.
- No personal or health data, and no secrets, in item names or descriptions.
- The Zoho tool names in `allowed-tools` belong to this account's connector (`claude_ai_Zoho_MCP_Atreya`). Another workspace's connector needs these names updated.

## Additional resources

- **`references/zoho-mapping.md`**: the config format, the ID resolution calls, the item-creation order and fields, and idempotency
