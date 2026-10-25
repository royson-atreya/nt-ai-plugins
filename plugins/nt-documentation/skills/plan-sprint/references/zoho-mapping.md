# Zoho Sprints mapping for plan-sprint

## Config file: `$NT_DOCS_DIR/sprint-plans/zoho-config.json`

Created on the first run after the user confirms it, then reused. It contains IDs only, no tokens or credentials.

```json
{
  "schema_version": 1,
  "teamId": "<numeric workspace id, from the user>",
  "project": {"key": "P7", "id": "<projectId>", "name": "<project name>"},
  "backlogId": "<from GetProjectDetails action=getbacklog>",
  "itemTypes": {"story": "<projitemtypeid>", "task": "<projitemtypeid>", "bug": "<optional>"},
  "priorities": {"high": "<projpriorityid>", "medium": "<projpriorityid>", "low": "<projpriorityid>"},
  "linkTypeId": "<id of a 'relates to' / 'parent of' link type, or null if none found>",
  "confirmed_at": "<date>"
}
```

## Resolving the IDs (read-only calls)

Every Zoho call takes headers `{"x-za-ui-version": "v2", "X-convert-response": "true"}`.

| Need | Call | Notes |
|---|---|---|
| teamId | ask the user | Zoho Sprints → Settings → Workspace, or the numeric id in the workspace URL. No tool returns it. |
| P7 project | `ZohoSprints_GetProjects` (`action=data`, `index=1`, `range=250`, `projectstatus=1`) | Match the project whose key, prefix, number or name is "P7". If several or none match, show the candidates and ask. Use `searchvalue` to narrow. |
| backlog | `ZohoSprints_GetProjectDetails` (`action=getbacklog`) | Items go in the backlog: pass `backlogId` as `sprintId`. |
| item types, link types | `ZohoSprints_GetProjectDetails` (`action=details`) | Find the item type ids named like Story/User Story and Task in the layouts or item types section, and a link type such as "relates to" or "parent of". |
| priorities | `ZohoSprints_GetProjectPriorities` (`action=data`, `index=1`, `range=50`) | Map the names to high, medium and low. If P7 uses other names, ask the user to map them. |

Show the resolved config to the user and get a yes before writing the file.

## Creating items (write calls; the plugin hook asks before each one)

Order: epic → stories → tasks → links.

1. **Epic**: `ZohoSprints_CreateEpic` with body `{"name": "<change request title>", "desc": "<summary + estimate + impact report path>"}`.
2. **Story**: `ZohoSprints_CreateItem` with `sprintId=backlogId`, `name=<S1 title>`, `projitemtypeid=itemTypes.story`, `projpriorityid=priorities[<priority>]` and `epicid=<epic id>`. The description holds the story description, the acceptance criteria as a bullet list, the modules, `Estimate: <sum of task min>–<sum of task max> person-days (from impact report)`, and `Ref: <impact report path> S1`.
3. **Task**: `ZohoSprints_CreateItem` with `projitemtypeid=itemTypes.task`, the story's priority and the same `epicid`. The description holds the task description, the discipline, `Estimate: <min>–<max> person-days`, the files hint, `Part of: S1 <story title>`, and `Ref: <impact report path> S1-T1`.
4. **Link** each task to its story with `ZohoSprints_LinkItems`: `itemId=<story item id>`, `sprintId=linktosprintid=backlogId`, `linktoprojectid=projectId`, `linktypeid=linkTypeId`, and `linkitemobj` containing the task item ids (JSON). If `linkTypeId` is null, skip linking, because the "Part of" line already carries the relationship.

Do not set `point`, `duration`, `users`, `startdate` or `enddate`. Estimates live in the description only.

## Idempotency

Before creating anything, check the `zoho` section of the work items block. If it covers every key and `links_done` is true, the plan was already pushed: show the refs and stop, unless the user asks for a re-push of specific stories. If it is partial, resume by creating only the missing keys. After each successful create, write the returned id into the block immediately (`work_items.py update`), so a run that fails halfway can resume without duplicating items.
