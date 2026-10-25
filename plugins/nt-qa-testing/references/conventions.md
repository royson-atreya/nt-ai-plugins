# nt-qa-testing conventions

Every skill and agent in this plugin follows these rules. Read this file, `qa-scope-rules.md` and (for `report`) `workbook-columns.md` before doing any work.

## Paths

| What | Default | Override |
|---|---|---|
| Specs (read-only input, written by nt-documentation) | `~/atreya-ai/nt-docs` | `NT_DOCS_DIR` |
| QA output | `~/atreya-ai/nt-docs/qa/<run-id>/` | follows `NT_DOCS_DIR` |
| Product repos (never read for test design, never written) | `~/atreya-ai/repos` | `NT_REPOS_DIR` |

- `bare_script.py` in skills and agents is shorthand for `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bare_script.py"`.
- When a skill starts an agent, the agent prompt **always** begins with `plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>` plus the absolute paths the agent needs (`docs_dir`, `run_dir`, `out_dir`), then the task inputs. Agents may not see `${CLAUDE_PLUGIN_ROOT}` expanded.
- Timestamps in folder names come from `date +%Y%m%d-%H%M`; never guess the time.

## Hard rules

1. **Test only what was given.** One task, bug or module per run. Never the whole project.
2. **Cases come from the spec, never from the code.** Do not open files under `~/atreya-ai/repos` to design, run or judge tests. If no spec covers the item, stop and suggest `/nt-documentation:analyze web <module>` or `/nt-documentation:impact "<change>"`. Exception: for a **bug**, the reproduction steps and expected behaviour the user gives are the spec.
3. **Never write product code**, test code for the repos, or anything inside `~/atreya-ai/repos`. Write only under the run dir.
4. **Web staging only** (`staging-dashboard.naditarangini.com`, API `staging-api.ashoka.world`). Production hosts are blocked by a hook. No mobile in v1.
5. **Credentials by placeholder only.** Type `{{nt-qa:<role>:username}}` and `{{nt-qa:<role>:password}}` (role = `doctor`, `admin`, `patient`, `college`). A hook swaps in the real value inside `browser_type` / `browser_fill_form` and masks it in tool output as `●●●●`. Never ask for, print, guess or write a real credential.
6. **Dummy data only.** Never real patient data; never copy names, phones, emails or readings out of specs, screens or API responses into QA files.
7. **Never read secrets**: `.env*`, `*.jks`, `*.keystore`, `firebase-*.json`, `google-services.json`, `GoogleService-Info.plist`. A hook enforces this.
8. **No git writes** (commit, push, pull). A hook enforces this.

## Spec sources (strongest first)

| Source | Path under docs dir | Use for |
|---|---|---|
| Impact report | `impact/<date>-<slug>.md` | change scope, affected screens/APIs, knock-on checks |
| Module analysis | `<Repo>/modules/<module>.md` | functional spec: flows, rules, validation, roles |
| Journey | `journeys/<name>.md` | end-to-end user flows across modules |
| API links | `api-links/api-links.json` (`.md`) | which web screen calls which API |
| Module map | `<Repo>/module-map.json` (`.md`) | module ids, screens, ownership |
| User-supplied bug | inline text or file | repro steps + expected behaviour (bugs only) |

`<Repo>` is the full repo directory name: `Nadi-Tarangini-Frontend` (web), `Ashoka-World-Backend` (backend), `Nadi-Tarangini-App` (mobile, out of scope in v1 except as context). Note each spec's `generated_at` and `graph_stale` stamp in `plan.md`; a stale spec lowers confidence.

## Run id and folder

- Run id: the given id if it looks like one (`NT-BUG-142`, `ZS-1234`, letters/digits/hyphens), else a kebab-case slug of the title (max 6 words). Modules: `module-<module-id>`. Uppercase is kept.
- **Resolving the run in later skills:** if the first argument word is a folder in `qa/`, use it. A case id `TC-<run-id>-NN` implies its run id. Otherwise run `ls -t <docs>/qa`, skip names containing `-old-`, take the first, say which one, and treat the whole argument as the skill's other input (e.g. a change request for `cases`).
- If `<docs>` does not exist, stop: "nt-docs not found at <path>; set NT_DOCS_DIR or run `/nt-documentation:map web` first".

```
qa/<run-id>/
├── bug.md                  # plan (bug runs): the user's bug report, verbatim
├── plan.md                 # plan
├── cases.md                # cases
├── screenshots/<case-id>-sNN.png
├── run.json                # run-web (web-runner)
├── check.md, check.json    # run-web (result-checker)
├── report.md, results.csv  # report
├── retest-<YYYYMMDD-HHMM>/ # retest: screenshots/, run.json, check.md, check.json, retest.md, results.csv
├── rerun-<YYYYMMDD-HHMM>/  # run-web on a subset of cases: screenshots/, run.json, check.*, results.csv
└── previous-<YYYYMMDD-HHMM>/ # an earlier full run, moved aside when run-web overwrote it
```

Every markdown file starts with front-matter:

```yaml
---
generated_by: nt-qa-testing/<skill or agent>
generated_at: <ISO timestamp>
run_id: <run-id>
kind: task | bug | module
environment: web-staging
---
```

## cases.md format (parsed by scripts; keep exactly)

```markdown
## TC-<run-id>-01 · <short scenario title> [bug-repro]
- Module: <module id or name>
- Sub-module: <screen / sub-area>
- Priority: P1
- Role: doctor
- Spec: <docs-relative path>#<section> | bug report
- Status: Ready
- Preconditions: <state needed, roles by placeholder only>
- Test data: <dummy values, or "none">

Steps:
1. <action> → Expected: <observable result>
2. <action> → Expected: <observable result>

Expected result: <overall pass condition>
```

- Case ids are `TC-<run-id>-NN`, numbered from 01 in order. `[bug-repro]` marks the cases that reproduce the bug (always first for a bug run); `retest` re-runs only those.
- `Status` in cases.md is one of `Ready`, `Skipped (R<n>: <reason>)`, `Blocked (<reason>)`. A case whose role may not be configured stays `Ready`: web-runner marks it Blocked at run time when the credential hook says the role is missing, so configuring the role later unblocks it without regenerating cases.
- `Priority`: P1 = the change/bug itself, P2 = validation and edge cases of it, P3 = regression of neighbours named in the spec.

## Test data

Every value is visibly fake and prefixed so it is easy to find and clean on staging:

| Kind | Pattern |
|---|---|
| Name | `QA-AUTO <Role> <run-tag>` e.g. `QA-AUTO Patient 0142` |
| Email | `qa.auto+<run-tag>@example.com` |
| Phone | `90000<5 digits>` (e.g. `9000000142`) |
| Date of birth | `1990-01-01` unless the case tests age rules |
| Free text | `QA-AUTO test note <run-tag>` |

`<run-tag>` is the last 4 digits of the run id, or 4 digits of the current time.

## Statuses

| Status | Meaning |
|---|---|
| Pass | every step's expected result observed (confirmed by result-checker) |
| Fail | at least one expected result not met; the first failing step is named |
| Blocked | could not run: missing role config, staging down, precondition not met, run aborted |
| Skipped | excluded by a scope rule (cite it) |

## Hand-off files

`run.json` (written by web-runner, observations only; no verdicts on Pass/Fail):

```json
{
  "run_id": "NT-BUG-142", "mode": "run", "base_url": "https://staging-dashboard.naditarangini.com",
  "started_at": "...", "finished_at": "...",
  "cases": [
    {"id": "TC-NT-BUG-142-01", "state": "executed | blocked | skipped | aborted", "reason": "",
     "steps": [{"n": 1, "action": "...", "url": "https://staging-dashboard...", "observed": "...",
                "screenshot": "screenshots/TC-NT-BUG-142-01-s01.png", "console_errors": []}]}
  ]
}
```

`check.json` (written by result-checker, the only source of Pass/Fail):

```json
{"run_id": "...", "checked_at": "...",
 "cases": [{"id": "TC-NT-BUG-142-01", "verdict": "Pass | Fail | Blocked | Skipped",
            "failed_step": null, "actual": "<one-line observed result>",
            "mismatches": [{"step": 2, "expected": "...", "observed": "...", "evidence": "screenshots/..."}],
            "confidence": "high | medium | low"}]}
```
