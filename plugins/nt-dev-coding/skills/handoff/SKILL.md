---
name: handoff
description: This skill should be used when the user asks to "hand off <id>", "write the handoff", "give me the commit message for <id>", "what do I test after deploy", "prepare <id> for QA", or runs /nt-dev-coding:handoff. Writes nt-docs/dev/<id>/handoff.md for one reviewed Nadi Tarangini task or bug: summary, files changed with +/- counts, review result, a suggested commit message per repo, deploy notes, and a staging retest plan in nt-qa-testing case format. Never commits or runs git writes.
argument-hint: "[id]"
disable-model-invocation: true
allowed-tools: Read, Glob, Write, Bash(python3:*), Bash(date:*), Bash(cat:*), Bash(ls:*), AskUserQuestion
---

# handoff: hand-off note, commit message and retest plan

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` first. `<docs>` is `$NT_DOCS_DIR` or `~/atreya-ai/nt-docs`; `<task_dir>` is `<docs>/dev/<id>` as an absolute path. The user does all git actions: write commands for them, never run them.

## 1. Resolve and check

The argument is the id; without one use `cat <docs>/dev/ACTIVE` and say which. If that is empty, `ls -t <docs>/dev` and ask. Read `ticket.md`, `plan.md`, `implement.md`, `review.md`, and `bug.md` for a bug. The kind comes from plan.md's front-matter.

- No `review.md`: say the change has not been reviewed and recommend `/nt-dev-coding:review <id>` first; continue only if the user insists, and mark the hand-off "NOT REVIEWED".
- Verdict `CHANGES REQUIRED` with open P1 findings: warn and ask whether to hand off anyway; if yes, list the open P1s at the top.

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/diffstat.py" <id> --json` (writes nothing) and compare its `diff_sha256` with `reviewed_diff_sha256` in review.md's front-matter. If they differ, or review.md has no `reviewed_diff_sha256`, the code changed after review (or the review cannot be matched to it): warn, recommend `/nt-dev-coding:review <id>`, and continue only if the user insists, marking the hand-off "CODE CHANGED SINCE REVIEW". Use this JSON (not diff.md) for the files table below.

## 2. Write handoff.md

`<task_dir>/handoff.md`, front-matter per conventions.md (`generated_by: nt-dev-coding/handoff`, `kind`), then:

1. **Summary**: what changed and why in 3–5 lines (product terms first, then technical), root cause for a bug, the acceptance criteria ids it covers.
2. **Files changed**: table `Repo | File | Status | + | − | Note` from the JSON (rows with status `-` are planned-unchanged: list them under the table instead), with totals per repo.
   - `mixed` files: note "contains the task change plus earlier uncommitted edits: review the hunks before adding (`git add -p`)".
   - `pre-existing` files: list them separately under "Not part of this task: do not commit unless intended".
   - `unplanned` and `secret` files: flag them.
3. **Review result**: verdict, counts by severity, open findings (id, sev, one line), accepted risks.
4. **Checks**: from implement.md (command → result).
5. **Deploy notes**: per repo, deploy order when several repos change (backend before web and app; the app needs a new build and old versions stay live), new migrations to run **on staging** (file names; never from the local backend checkout, whose `.env` points at production), config/env **key names** to add (never values), cache or queue restarts the user must do.
6. **Suggested commit message**, one per repo, in a fenced block:

   ```
   <type>(<module>): <imperative summary ≤ 72 chars>

   <what and why, 2–4 lines wrapped at 72>

   Refs: <id>
   ```

   `type` is `fix` for a bug, `feat` for new behaviour, `refactor`/`chore` only when the plan says so. Follow it with the commands **for the user** to review and run themselves:
   - `git -C <root> status`
   - `git -C <root> add <the task's files, listed explicitly>`: only files that are planned and changed. Never secret, unplanned or pre-existing files. Use `git add -p <file>` for mixed files.
   - `git -C <root> commit -m "<summary line>" -m "<body>" -m "Refs: <id>"`

7. **Retest plan (staging, after deploy)** in the nt-qa-testing `cases.md` case format, case ids `TC-<id>-NN`:

   ```markdown
   ## TC-<id>-01 · <short scenario>
   - Module: <module id>
   - Sub-module: <screen / sub-area>
   - Priority: P1
   - Role: doctor
   - Spec: dev/<id>/ticket.md#acceptance-criteria
   - Status: Ready
   - Preconditions: <state needed; roles by placeholder only>
   - Test data: <QA-AUTO dummy values, or "none">

   Steps:
   1. <action> → Expected: <observable result>

   Expected result: <overall pass condition>
   ```

   - **Bug only:** the reproduction steps come first as cases whose title ends with ` [bug-repro]` and whose expected result is the correct behaviour. Tasks have no `[bug-repro]` cases.
   - P1 = each acceptance criterion; P2 = validation and edge cases of the change; P3 = regression of consumers listed in review.md "Side effects on other modules".
   - Test data follows nt-qa-testing conventions (`QA-AUTO <Role> <tag>`, `qa.auto+<tag>@example.com`, `90000xxxxx`). Never real data, never credentials.
   - nt-qa-testing v1 runs web staging only: cases for the app or a pure API get `Status: Skipped (R6: not web staging, test manually on <app flavor | API>)`.

8. **Next steps**: after the user deploys to staging, start QA with `/nt-qa-testing:plan <task_dir>/handoff.md` and use `<id>` as the QA run id so the case ids line up. nt-qa-testing still builds its scope from the nt-docs specs and writes its own cases.md; this retest plan is its input. Then `/nt-qa-testing:cases <id>` → `run-web` → `report`; for a bug, `/nt-qa-testing:retest <id>` once that QA run exists.

## 3. Report

Show the user the summary, the files table totals, the review verdict, the commit message(s), the deploy notes, and the number of retest cases (by priority), plus the path of handoff.md. Do not commit, push or switch branches.
