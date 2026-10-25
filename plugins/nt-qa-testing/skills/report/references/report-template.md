# report.md template

```markdown
---
generated_by: nt-qa-testing/report
generated_at: <ISO timestamp>
run_id: <run-id>
kind: task | bug | module
environment: web-staging
---

# QA report: <title from plan.md> (`<run-id>`)

**Result: <All N cases passed | F of N failed | B blocked, see below>**
<For a bug run: "Bug reproduced on staging" | "Bug not reproduced: all repro cases passed" | "Bug reproduction inconclusive: <reason>". Add "Latest retest (<ts>): FIXED" if a retest exists.>

| Pass | Fail | Blocked | Skipped | Not run | Total |
|---|---|---|---|---|---|
| 9 | 2 | 1 | 3 | 0 | 15 |

| Priority | Pass | Fail | Blocked | Skipped |
|---|---|---|---|---|
| P1 | | | | |
| P2 | | | | |
| P3 | | | | |

## Failures
### TC-<run-id>-04 · <scenario> (P1)
- **Failing step:** 3. <action>
- **Expected:** <expected>
- **Observed:** <observed, from check.json>
- **Evidence:** [step 3](screenshots/TC-<run-id>-04-s03.png) · [step 2](screenshots/TC-<run-id>-04-s02.png)
- Confidence: high

## Blocked
| Case | Reason |
|---|---|

## Skipped (scope rules)
| Case | Rule | Reason |
|---|---|---|

## All cases
| Case | Scenario | Priority | Verdict | Actual |
|---|---|---|---|---|

## Environment
- Base URL: https://staging-dashboard.naditarangini.com
- Run: <started_at> → <finished_at>
- Roles used: doctor, admin
- Specs: <paths + generated_at from plan.md>; <stale warning if any>

## Files
`plan.md` · `cases.md` · `run.json` · `check.md` · `results.csv` · `screenshots/`
```

Notes:

- Omit empty sections (e.g. no Failures) instead of leaving empty tables, but keep the totals table.
- Observed text comes from check.json; do not rephrase it into something softer.
