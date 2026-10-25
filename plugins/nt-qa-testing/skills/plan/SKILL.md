---
name: plan
description: This skill should be used when the user asks to "plan testing for <task>", "what should we test for this bug", "QA plan for <module>", "test this bug on staging", "start QA for <change>", or runs /nt-qa-testing:plan. Entry point of a QA run: turns ONE Nadi Tarangini task, bug or web module into a test scope (what to test, why, which screens/APIs/roles) from verified nt-docs specs or the user's bug report, never from code. Not for change-impact analysis or effort estimates (use /nt-documentation:impact).
argument-hint: <task | bug report | module id, as text or a path to a .md/.txt file>
allowed-tools: Read, Glob, Grep, Write, Bash(python3:*), Bash(mkdir:*), Bash(mv:*), Bash(date:*), Bash(ls:*), AskUserQuestion
---

# plan: test scope for one task, bug or module

Produce `<docs>/qa/<run-id>/plan.md` (and `bug.md` for a bug) following `references/plan-template.md` in this skill folder.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` and `${CLAUDE_PLUGIN_ROOT}/references/qa-scope-rules.md` first. `<docs>` is `$NT_DOCS_DIR` or `~/atreya-ai/nt-docs`; if it or `<docs>/module-index.md` is missing, stop and suggest setting NT_DOCS_DIR or running `/nt-documentation:map web`.

**Never open files under `~/atreya-ai/repos` or any source code**, even when a spec cites `path:line`. Scope comes from nt-docs specs, or for a bug from the user's report.

## 1. Read the input and classify it

If the argument is a path, read the file. With no argument, ask what to test.

| Kind | Signals |
|---|---|
| bug | words like bug, defect, issue, "steps to reproduce", "expected/actual", a bug id (`NT-BUG-142`, `ZS-1234`) |
| module | the text is (or names) a web module id or name from `Nadi-Tarangini-Frontend/module-map.json`, e.g. `patients`, "test the appointments module" |
| task | anything else: a feature, change request or story |

When it is genuinely ambiguous, ask once with AskUserQuestion. Pick the run id per conventions.md. If `qa/<run-id>/` already exists, ask: continue (keep files), start fresh (rename the old folder to `<run-id>-old-<ts>` with `mv`; `<ts>` from `date +%Y%m%d-%H%M`), or use `<run-id>-2`. When continuing and `cases.md` or `run.json` exists, warn at the end that they are stale if the plan changed, and recommend regenerating with `/nt-qa-testing:cases <run-id>`.

Create `qa/<run-id>/` now (`mkdir -p`).

## 2. Bug: capture the report (the bug's own spec)

A bug needs: title, reproduction steps, expected behaviour, actual behaviour, role (doctor/admin/patient/college), and the screen or staging URL. If steps or expected behaviour are missing, ask for them and stop until answered; do not guess. Role and screen may be inferred from the steps (say so).

If the report contains anything that looks like a real username, password, phone, email or patient name, ask the user to replace it before saving; never store it. Then save the report verbatim (with front-matter) as `qa/<run-id>/bug.md`.

A bug can proceed without an nt-docs analysis. Still run step 3 to find context (screens, related APIs, knock-on checks); mark it optional.

## 3. Find the specs

Extract 2–6 search terms (domain nouns, screen names, module ids; take vocabulary from `<docs>/module-index.md`). Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/find_spec.py" <term> <term> ... [--module <web-module-id>]
```

Refine terms if results are empty or too broad. Then read, strongest first: matching impact reports, the module analyses listed in `specs` (Part 1 functional spec, plus 2.1 APIs and 2.5 screens), relevant journey sections, and the module map entries. Read only the sections needed.

**Stop rule (task or module):** if `spec_level` is `map-only` or `none`, i.e. no impact report, module analysis or journey covers the item, do not write a plan. Tell the user what was found and suggest, as fits:

- `/nt-documentation:analyze web <module-id>` (for the main web module), and/or the backend module it fronts
- `/nt-documentation:impact "<the change>"` (for a change request)

Never fall back to reading code. For a bug, continue using the bug report as the spec.

Module map entries with status `not-in-use` are out of scope unless the user named them; say so.

## 4. Decide the scope

From the specs (or bug report), list:

- **In scope:** each behaviour to test, why (the change, the bug, a business rule, a knock-on effect), its screen(s), API(s) from api-links, role(s), and the spec section it comes from.
- **Regression (P3):** only neighbours the spec's knock-on / "used by screens" sections name.
- **Out of scope:** everything else that a reader might expect, with the reason (other module, not-in-use, mobile, scope rule).
- **Scope rules applied:** which of R1–R7 affect this run and how (e.g. "R2: OTP login cases skipped; request-OTP form validation in scope").
- **Languages:** only if the screens have a language selector; only R5 languages.
- **Spec freshness:** each spec's path, `generated_at`, `graph_stale`. A stale spec or a draft map lowers confidence; say so.
- **Risks and open questions:** spec gaps that will limit expected results.

Keep it to the given item. A plan for one bug normally has 1–3 screens.

## 5. Write and hand back

Write `plan.md` following `references/plan-template.md`; tag open questions that prevent writing expected results `[blocking]`. Then show the user, briefly: run id (say "use `<run-id>` for cases, run-web, report and retest"), kind, in-scope screens/APIs/roles, rules applied, open questions, and the path. Ask them to review the plan and run `/nt-qa-testing:cases <run-id>` when it is right. Do not start case design in the same turn.

## Additional resources

- **`references/plan-template.md`**: plan.md layout.
- **`${CLAUDE_PLUGIN_ROOT}/scripts/find_spec.py`**: deterministic spec lookup in nt-docs.
