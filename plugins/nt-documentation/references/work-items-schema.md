# Proposed work items schema (v1)

`impact` ends its report with this block and `plan-sprint` reads it. Keep the schema stable, and bump `schema_version` for any breaking change.

The block sits at the end of `$NT_DOCS_DIR/impact/<date>-<slug>.md`, fenced like this:

````markdown
## Proposed work items

<!-- nt-work-items:start -->
```json
{ ... }
```
<!-- nt-work-items:end -->
````

```json
{
  "schema_version": 1,
  "change_request": "Short restatement of the request",
  "impact_report": "impact/2026-10-25-medicine-expiry-alerts.md",
  "estimate_unit": "person-days",
  "contingency_pct": 20,
  "status": "proposed",
  "stories": [
    {
      "key": "S1",
      "title": "Track expiry date per medicine batch",
      "description": "Why and what, in plain language.",
      "modules": ["backend:medical-inventory", "web:medical-inventory", "app:inventory"],
      "priority": "high",
      "acceptance_criteria": [
        "Doctor can enter an expiry date when adding stock",
        "Medicines expiring in 30 days are listed on the inventory screen"
      ],
      "tasks": [
        {
          "key": "S1-T1",
          "title": "Add expiry_date to doctor_medicine_inventory + migration",
          "discipline": "backend",
          "estimate_days": {"min": 0.5, "max": 1},
          "description": "Technical notes.",
          "files_hint": ["app/Http/Controllers/MedicalInventory/MedicineController.php"],
          "depends_on": []
        }
      ]
    }
  ]
}
```

## Rules

- `discipline` is one of `backend`, `web`, `app`, `qa`, `devops`, `design`.
- Every story gets at least one `qa` task. QA effort counts toward the totals.
- `estimate_days` are ranges in person-days. Totals and contingency are computed, not written by hand: total min/max = the sum of the tasks; with contingency = total × (1 + contingency_pct/100).
- `modules` use `<repo-alias>:<module-id>` with ids from the module maps.
- `files_hint` is a hint only, never a promise. Use paths from the impact analysis.
- `status` stays `proposed` until the user approves. plan-sprint then sets `status: "approved"` and `approved_at`, and records either `task_list_file` (when there is no Zoho connector) or `zoho`, filled in as each item is created:

  ```json
  "zoho": {"project_id": "<id>", "epic_id": "<id>", "stories": {"S1": "<item id>"}, "tasks": {"S1-T1": "<item id>"}, "links_done": false}
  ```

  When `zoho` covers every story and task key and `links_done` is true, the push is complete. A partial `zoho` means an interrupted push that plan-sprint can resume.
- To change the block, run `work_items.py extract <report> > <tmp.json>`, edit the JSON, then run `work_items.py update <report> <tmp.json>`. Keep the temp file under `$NT_DOCS_DIR/sprint-plans/.wi-<slug>.json`.
- No personal or health data, and no secrets.
