---
name: impact
description: This skill should be used when the user asks "what is the impact of <change>", "which modules/screens/APIs/tables does this change affect", "estimate this change request", "impact analysis for <feature>", "how big is this change", or runs /nt-documentation:impact. Produces a change-impact report across the three Nadi Tarangini repos (affected modules, screens, APIs and tables, knock-on effects, risks, and a person-day estimate with proposed work items for plan-sprint).
argument-hint: <change request text | path to a file containing it>
allowed-tools: Bash(python3:*), Bash(jq:*), Bash(git -C:*), Read, Glob, Grep, Write, Edit, AskUserQuestion
---

# impact: change-impact analysis

Turn a change request into `$NT_DOCS_DIR/impact/<YYYY-MM-DD>-<slug>.md`, following `references/impact-report-template.md` (in this skill folder). The report ends with a "Proposed work items" JSON block in the format given by `${CLAUDE_PLUGIN_ROOT}/references/work-items-schema.md`, which `plan-sprint` consumes.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` first. Analysis only: never write product code, tests or UI, even as an illustration of the change.

## Inputs, from strongest to weakest

1. Confirmed module maps, `modules/<id>.md` docs, and `api-links/api-links.json` in `$NT_DOCS_DIR`
2. `${CLAUDE_PLUGIN_ROOT}/scripts/impact_seed.py` (deterministic matching plus knock-on expansion)
3. `graph_query.py`, `laravel_routes.py` and `laravel_data.py` queries
4. Targeted reads of source files (a few line ranges, never whole folders)

Fewer strong inputs means lower confidence. Say so in the report instead of filling gaps by guessing.

## Workflow

### 1. Understand the request

If the argument is a file path, read it. Restate the request in one paragraph. When it is ambiguous in a way that changes the scope (for example "add expiry alerts": in-app only, or also WhatsApp through Interakt?), ask up to three questions with AskUserQuestion before analysing. Otherwise state your interpretation and continue.

### 2. Check inputs and freshness

Run `graph_query.py stamp` for all three repos. Note the status of each module map (confirmed, draft or missing), whether `api-links.json` exists, and its date. If `api-links.json` is missing, offer to run `/nt-documentation:link-apis` first, because without it screen-level impact is weak.

### 3. Seed

Extract 3–8 search terms: domain nouns, likely table, controller and screen names, and URIs. Take vocabulary from `${CLAUDE_PLUGIN_ROOT}/references/domain-glossary.md` and the module map summaries. Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/impact_seed.py" <term> <term> ... --limit 25
```

Iterate on the terms if the results are empty or too broad. For example, add table names found in the first pass. Keep the term list in the evidence log.

### 4. Confirm and expand

Work on the candidate modules with a seed score of 3 or more, or the top 8 candidates, whichever list is longer. For each one:

- Read its `$NT_DOCS_DIR/<repo-name>/modules/<id>.md` (sections 1.3–1.5 and 2.1–2.3) if it exists. If it doesn't, check routes, tables and one or two key files directly, and mark confidence lower.
- Decide the change type (new, modify, config, or verify-only), and record the evidence as `path:line` or a seed or api-links row.
- Expand the **knock-on effects**: every writer and reader API of a changed table (from the seed's table section), every client screen of a changed API (api-links), graph callers of changed services, crons, report generators (PDF and Lambda), and external payloads.
- Leave candidates that turn out unrelated in section 8 ("not affected"), with the reason.

Check `${CLAUDE_PLUGIN_ROOT}/references/not-in-use.md`: unused features are out of scope unless the request names them. Check `${CLAUDE_PLUGIN_ROOT}/references/external-systems.md` for cross-system impact.

### 5. Work items (the estimate is built from these)

Write stories and tasks following `${CLAUDE_PLUGIN_ROOT}/references/work-items-schema.md`, with at least one QA task per story, `status: "proposed"`, and keys `S1`, `S1-T1`, and so on. Give every task a person-day range. Never estimate a discipline without tasks behind it. Choose the contingency: 20% by default, 30–40% when confidence is low or when schema or data migrations or external systems are involved. **Set `contingency_pct` in the JSON to that value**, because the totals are computed from it. Give no calendar dates.

### 6. Write the report

Write `$NT_DOCS_DIR/impact/<YYYY-MM-DD>-<slug>.md` following the template, creating `impact/` if needed. The slug is a kebab-case version of the restated title (maximum 6 words). Put the work items JSON in section 11 between the `nt-work-items` markers. Leave the numbers in section 10 and the estimate line in section 2 as `TBD` for now.

### 7. Validate and fill in the totals

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/work_items.py" check <report.md>
```

Fix any ERROR lines in the JSON and re-run until it exits 0. Then use Edit to replace the `TBD`s: copy the per-discipline totals it prints into the section 10 table (one row per discipline it lists), and the total and with-contingency figures into section 2. This keeps the tables equal to the sum of the tasks. List the assumptions under the table.

### 8. Report

Reply with:

- the path
- the summary block (counts, estimate, confidence, top risks)
- the number of stories and tasks
- the next step: review the report, then `/nt-documentation:plan-sprint <report path>` once the work items look right. plan-sprint will not create anything without explicit approval.

## Rules specific to impact

- Every affected item cites evidence. Mark anything inferred `(inferred)`.
- Prefer listing a knock-on item as "verify-only" over leaving it out silently.
- Do not create or modify Zoho items here. That is plan-sprint's job, and it needs approval.
- No personal or health data, and no secrets, in examples or acceptance criteria.

## Additional resources

- **`references/impact-report-template.md`**: the section layout and tables
- `${CLAUDE_PLUGIN_ROOT}/references/work-items-schema.md`: the work items JSON contract shared with plan-sprint
- `${CLAUDE_PLUGIN_ROOT}/scripts/impact_seed.py --help`
