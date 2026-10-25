# Impact report template: `$NT_DOCS_DIR/impact/<YYYY-MM-DD>-<slug>.md`

```markdown
---
generated_by: nt-documentation/impact
generated_at: <date>
change_request: "<one line>"
confidence: high|medium|low
sources:
  - repo: Ashoka-World-Backend
    commit: <sha>
    graph_stale: false
  - repo: Nadi-Tarangini-Frontend
    commit: <sha>
  - repo: Nadi-Tarangini-App
    commit: <sha>
inputs:
  module_maps: {backend: confirmed|draft|missing, web: …, app: …}
  api_links: <generated_at or missing>
  module_docs_used: [Ashoka-World-Backend/modules/medical-inventory.md, …]
---

# Impact: <title>

## 1. Change request
The request as given (quoted), then a restatement in one paragraph. List any interpretation choices you made.

## 2. Summary
- Affected: N modules, N screens, N APIs (N new, N changed), N tables (N schema changes)
- Estimate: **X–Y person-days**, or X'–Y' with Z% contingency
- Confidence: high / medium / low, and why (e.g. "2 of 4 modules have no analyze doc")
- Top risks: up to three bullets

## 3. Affected modules
| Repo | Module | Map status | Change type (new/modify/config/none-verify) | Why (evidence) | Confidence |
|---|---|---|---|---|---|

## 4. Affected screens
| Client | Screen (file) | What changes for the user | Evidence |
|---|---|---|---|

## 5. Affected APIs
| Method URI | Controller@action | Change (new / modify request / modify response / behaviour) | Clients that call it | Evidence |
|---|---|---|---|---|

Include **knock-on** APIs: other endpoints that read or write a changed table, or call changed services, even when the request doesn't mention them.

## 6. Affected tables
| Table | Connection | Change (new column / new table / data migration / read-only impact) | Writers | Readers | Evidence |
|---|---|---|---|---|---|

## 7. External systems and non-code impact
Lambdas, Razorpay, ENACH, Interakt, ZeptoMail, the BLE device, S3, crons and queues, plus config and env keys (names only), translations, report PDFs, and app-store release needs.

## 8. Out of scope / explicitly not affected
Things someone might assume are affected, with the reason they are not. Not-in-use features touched only incidentally go here.

## 9. Risks and open questions
Numbered. Each one has an owner role (product / backend / app / QA) where obvious.

## 10. Estimate
| Discipline | Min (d) | Max (d) | Basis |
|---|---|---|---|
| Backend | | | |
| Web | | | |
| App | | | |
| QA | | | |
| *(add a row for any other discipline `work_items.py check` prints: devops, design)* | | | |
| **Total** | | | sum of work items |
| **With contingency (Z%)** | | | |

Assumptions: list them, e.g. "one developer per discipline, no design work, existing test env".

## 11. Proposed work items
<!-- nt-work-items:start -->
```json
{ "schema_version": 1, … }
```
<!-- nt-work-items:end -->

## Evidence log
Commands run (impact_seed terms, graph queries, laravel_routes and laravel_data calls) and the files opened.
```
