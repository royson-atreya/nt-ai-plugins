# plan.md template

```markdown
---
generated_by: nt-qa-testing/plan
generated_at: <ISO timestamp>
run_id: <run-id>
kind: task | bug | module
environment: web-staging
specs:
  - path: <docs-relative path>
    generated_at: <date>
    graph_stale: false
---

# QA plan: <short title> (`<run-id>`)

> <One paragraph: what is being tested and why, in plain language. For a bug: the symptom and the
> expected behaviour. For a task: the change. For a module: the module's purpose.>

## 1. Source of truth
| Spec | Sections used | Freshness |
|---|---|---|
| `Nadi-Tarangini-Frontend/modules/patients.md` | 1.3 Features, 1.4 F2, 1.5 rules | 2026-10-26, graph fresh |
| bug report (`bug.md`) | steps, expected | user, <date> |

Confidence: high | medium | low, with the reason.

## 2. In scope
| # | Behaviour to test | Why | Screen(s) | API(s) | Role(s) | Spec ref |
|---|---|---|---|---|---|---|
| S1 | Add patient with mandatory fields only | changed by the task | Patient list → Add patient | POST /storePatient | doctor | patients.md#1.4-F2 |

## 3. Regression checks (P3)
| # | Neighbour | Why it could break | Spec ref |
|---|---|---|---|

## 4. Out of scope
| Item | Reason |
|---|---|
| Mobile app | v1 is web only |

## 5. Scope rules applied
- R2: <how it affects this run>

## 6. Languages
<"Not applicable: no language selector on these screens" or the R5 languages to cover and where.>

## 7. Test data needs
<dummy records the cases will create (QA-AUTO …), and staging preconditions such as "a doctor with at least one QA-AUTO patient".>

## 8. Risks and open questions
- [blocking] <gap that prevents writing expected results>
- <non-blocking gap, ambiguity, environment dependency>

## Next
Review this plan, then run `/nt-qa-testing:cases <run-id>`.
```

Notes:

- Every in-scope row cites a spec section or `bug report`. A row with no source does not belong in the plan.
- API column: method + URI from api-links; leave `-` when the screen calls none or the link is unknown.
- Use role names only, never account names.
