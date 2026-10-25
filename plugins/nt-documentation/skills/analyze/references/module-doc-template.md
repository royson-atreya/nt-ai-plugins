# Module doc template: `$NT_DOCS_DIR/<repo-name>/modules/<module-id>.md` (full repo name)

Fill every section. If a section has nothing, write "None found", followed by the queries that were run. Never leave a section out silently. Cite `path:line` for every claim. Tag judgement calls `(inferred)` and anything unconfirmed `TODO: verify`.

```markdown
---
generated_by: nt-documentation/analyze
generated_at: <date>
module: <module-id>
module_map_status: draft|confirmed
focus: <controller|flow or "full">
sources:
  - repo: <repo>
    commit: <sha>
    graph_commit: <sha>
    graph_stale: false
---

# <Module name> (`<module-id>`, <repo>)

> Status: live | not-in-use. Product area: <area>. Map status: <draft|confirmed>.
> One-paragraph summary a new team member can read in 30 seconds.

## Part 1: Functional spec

### 1.1 Purpose
What problem this module solves and for whom.

### 1.2 Actors and roles
| Actor | How identified in code | Can do |
|---|---|---|
| Doctor | `auth.token` middleware, `user_type = …` (path:line) | … |

### 1.3 Features
Numbered list. Each feature is one line of plain language followed by its evidence:
1. **Create a mandate**: the doctor registers a recurring debit. (`ENACHController::createMandate` path:line)

### 1.4 User flows (top 5–8, in depth)
For each flow:
- **Trigger:** the screen or action that starts it (web view / app screen, from api-links if available)
- **Steps:** a numbered list from the user's view, with the API called at each step
- **Outcome:** what changes (records created or updated, notifications sent, external calls)
- **Failure paths:** validation errors, auth failures, external-system failures, and what the user sees

Flows not covered in depth: list them as "summary only", one line each.

### 1.5 Business rules
| # | Rule | Where enforced (path:line) | Notes |
|---|---|---|---|
| BR-1 | A mandate amount must be ≤ plan price | `…Request.php:12` | |

Cover validation rules, permissions, status transitions, limits, pricing and free-trial logic, and time-based rules (crons). These rules are what QA tests against.

### 1.6 Edge cases and known gaps
Bullets: race conditions, missing validation, test-only endpoints, dead branches, TODOs in code. Note any "not in use" items here.

## Part 2: Technical reference

### 2.1 APIs
Every route in the module. Rows are grouped by controller.

| Method | URI | Controller@action | Auth / middleware | Request fields (validation) | Response (shape) | Depth |
|---|---|---|---|---|---|---|
| POST | /enach/create | ENACHController@create | auth.token | amount: required\|numeric … | `{status, data:{mandate_id}}` | deep / summary |

Request fields come from FormRequest classes or `$request->validate([...])`. Responses are described as a **shape**, never as sample values.

### 2.2 Data
| Table | Connection | Model | Access (R/W) | Key columns (names only) | Evidence |
|---|---|---|---|---|---|

Get this from `laravel_data.py <repo> uses <path>`. For web and app modules, write "via backend API" and link to the backend module doc.

### 2.3 External systems
| System | What for | Where called (path:line) | Failure handling |
|---|---|---|---|

Use the names in `references/external-systems.md`.

### 2.4 Dependencies
- **Depends on:** other modules, with what is used
- **Used by:** modules and screens (from module-map `depends_on` and the graph's "Used by"; for backend modules, the web and app screens from api-links)

### 2.5 Used by screens (backend modules only)
| Client | Screen / view | API | Evidence |
|---|---|---|---|

Get this from `$NT_DOCS_DIR/api-links/api-links.json`. If that file is missing, write: "api-links not generated yet; run /nt-documentation:link-apis."

### 2.6 Open questions / TODO: verify
A numbered list for the NT team to answer.

## Evidence log
The commands run and the key files opened, so the doc can be re-verified.
```
