# Writing flow pages for a module diagram

The overview page is generated (`drawio_build.py spec-module`). Flow pages are added by hand to the same spec, one page per flow written in full in `modules/<id>.md` section 1.4 (not the "summary only" list). Then rebuild.

## Page shape

```json
{
  "name": "Flow: Create mandate",
  "rows": "sequence",
  "lanes": [
    {"id": "user",     "label": "Doctor"},
    {"id": "client",   "label": "Web / App screen"},
    {"id": "backend",  "label": "Backend"},
    {"id": "data",     "label": "Database"},
    {"id": "external", "label": "External"}
  ],
  "nodes": [
    {"id": "s1", "lane": "user",    "kind": "step",  "label": "1. Opens Billing → Auto-pay"},
    {"id": "s2", "lane": "client",  "kind": "screen","label": "2. billing_details.blade.php\nPOST /createMandate", "source": "resources/views/my_account/billing_details.blade.php"},
    {"id": "s3", "lane": "backend", "kind": "api",   "label": "3. ENACHController@createMandate\nvalidates amount, plan", "source": "app/Http/Controllers/ENACH/ENACHController.php:42"},
    {"id": "s4", "lane": "data",    "kind": "table", "label": "4. enach_mandate (W)"},
    {"id": "s5", "lane": "external","kind": "external","label": "5. Mandate registration"},
    {"id": "s6", "lane": "client",  "kind": "step",  "label": "6. Shows mandate status"},
    {"id": "f1", "lane": "backend", "kind": "note",  "label": "Failure: invalid amount → 422 (BR-2)"}
  ],
  "edges": [
    {"from": "s1", "to": "s2"}, {"from": "s2", "to": "s3", "label": "POST /createMandate"},
    {"from": "s3", "to": "s4", "style": "data"}, {"from": "s3", "to": "s5", "style": "async"},
    {"from": "s5", "to": "s6"}
  ]
}
```

## Rules

- `rows: "sequence"` gives each node its own row, in array order, so list nodes in step order.
- Number step labels (`1.`, `2.`, …) to match the numbered steps in the analyze doc.
- Every `api`, `controller`, `service` and `screen` node needs a `source` (`path` or `path:line`). diagram-checker verifies each one.
- Put one or two key failure paths in `note` nodes, citing the business-rule id (`BR-n`) from the analyze doc.
- Keep a page to 12 nodes or fewer. Split longer flows into "part 1" and "part 2" pages.
- Never put personal or health data in labels. Use field names only.
- Lane ids are free-form, but keep the five-lane shape above for consistency across modules. Drop lanes the flow does not use.
