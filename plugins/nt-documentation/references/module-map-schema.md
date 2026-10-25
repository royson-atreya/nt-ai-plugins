# module-map.json schema (v1)

`map` writes this file and every other skill reads it. Later plugins (nt-qa-testing, nt-dev-coding) read it too, so keep the schema stable. Bump `schema_version` for any breaking change.

Location: `$NT_DOCS_DIR/<repo-name>/module-map.json`, where `<repo-name>` is the full repo directory name (e.g. `Ashoka-World-Backend`). The markdown file `module-map.md` next to it is **generated** from the JSON by `scripts/module_map.py render`. Never edit the markdown by hand.

```json
{
  "schema_version": 1,
  "status": "draft",
  "repo": "Ashoka-World-Backend",
  "commit": "<full sha>",
  "graph_commit": "<graphify built_at_commit>",
  "generated_at": "2026-10-25",
  "confirmed_at": null,
  "modules": [
    {
      "id": "nadi-pariksha",
      "name": "Nadi Pariksha",
      "product_area": "NadiPariksha",
      "kind": "product-area",
      "status": "live",
      "summary": "One or two sentences on what the module does for users.",
      "paths": [
        "app/Http/Controllers/NadiPariksha/*",
        "app/Models/NadiParikshaModels/*",
        "resources/views/nadi-pariksha/*"
      ],
      "entry_points": ["NadiParikshaController", "NPnadiController"],
      "route_prefixes": ["/nadi_pariksha", "/nadi-pariksha-admin"],
      "route_count": 120,
      "external_systems": ["AWS Lambda", "Razorpay"],
      "depends_on": ["core-auth", "core-reports"],
      "inferred": false,
      "evidence": [
        "graph_query.py folder backend app/Http/Controllers/NadiPariksha",
        "laravel_routes.py backend --by-controller"
      ],
      "notes": ""
    }
  ]
}
```

## Field rules

| Field | Rule |
|---|---|
| `status` (top level) | `draft` until the user approves the module list. `module_map.py confirm` sets `confirmed` and `confirmed_at`. |
| `id` | kebab-case, unique within the repo, and **stable**: keep ids the user already confirmed when re-mapping. The `analyze`, `diagram` and `impact` file names use it. |
| `product_area` | One of `NadiTarangini`, `NadiPariksha`, `Turyaa`, `Guna`, `ENACH`, `MedicalInventory`, `ResearchDashboard`, `Organization`, `NTAdmin`, `NTUser`, `External`, `V1`, `Core`, `Shared`. Web and app modules use the same values so `module-index.md` can line repos up. |
| `kind` | `product-area` (a backend area folder), `core` (a `core-*` group of root-level backend controllers), `feature` (a web or app feature folder), `shared` (shared widgets, constants, helpers, middleware), or `infra` (config, providers, console, jobs). |
| `status` (module) | `live`, `not-in-use` (listed in `references/not-in-use.md`), or `unknown`. |
| `paths` | fnmatch patterns relative to the repo root. `*` also crosses `/`. A file belongs to the module whose matching pattern is **longest** (most specific). Two modules matching a file with equal-length patterns is an overlap error. List root-level files (such as `app/Http/Controllers/PatientDetailsController.php`) explicitly. |
| `entry_points` | Backend: controllers. Web: controllers and main Blade views. App: screens or BLoCs that start the flow. |
| `route_prefixes`, `route_count` | Backend and web only, from `laravel_routes.py`. Use `[]` and `0` for the app. |
| `inferred` | `true` when the grouping is a judgement call rather than a folder boundary (every `core-*` module, for example). The user confirms these. |
| `evidence` | The commands or files that justify the grouping. |

## Code roots (used for coverage)

`module_map.py check` reports any graph source file under these roots that no module covers:

| Repo | Roots |
|---|---|
| Ashoka-World-Backend | `app/`, `resources/views/`, `routes/` |
| Nadi-Tarangini-Frontend | `app/`, `resources/views/`, `routes/`, `public/js/` (excluding minified and vendor libraries) |
| Nadi-Tarangini-App | `lib/` |

Aim for 100% coverage. Put leftovers in a `shared-*` or `infra-*` module rather than leaving them unassigned.
