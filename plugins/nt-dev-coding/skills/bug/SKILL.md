---
name: bug
description: This skill should be used when the user asks to "fix this bug", "plan a fix for <bug>", "find the root cause of <issue>", "write a bug ticket", "why does <screen> fail", or runs /nt-dev-coding:bug with a bug description or ticket text. Turns ONE Nadi Tarangini bug into a bug ticket (reproduction steps, expected/actual, suspected root cause with file:line, acceptance criteria) and a minimal fix plan from nt-docs specs and the code path, saves them to nt-docs/dev/<id>/, then stops for the user's approval. Never edits code. For new features use the task skill.
argument-hint: "<bug description | ticket text | path to a .md/.txt file> | <existing bug id> [what to change]"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Write, Edit, Bash(python3:*), Bash(mkdir:*), Bash(ls:*), Bash(date:*), Bash(cat:*), Agent, Task, AskUserQuestion
---

# bug: bug ticket, root cause and fix plan

Produce `<docs>/dev/<id>/bug.md`, `ticket.md` and `plan.md`, then **stop** for approval. Never edit anything in the product repos (`$NT_REPOS_DIR`, default `~/atreya-ai/repos`) from this skill.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` first. `<docs>` is `$NT_DOCS_DIR` or `~/atreya-ai/nt-docs`; if it does not exist, stop and suggest setting NT_DOCS_DIR or running `/nt-documentation:map all`.

**Existing id:** if the first argument word is a folder in `<docs>/dev/`, this is a re-plan: follow the `task` skill's steps 1R–6 (`${CLAUDE_PLUGIN_ROOT}/skills/task/SKILL.md`) with `kind=bug`. Never rewrite bug.md; append new information under its "Clarifications".

## 1. Capture the report

If the argument is a path, read it. A bug needs:

| Field | If missing |
|---|---|
| Title | derive from the text (say so) |
| Reproduction steps | **required** |
| Expected behaviour | **required** |
| Actual behaviour (error text, wrong value, crash) | ask |
| Where: web staging / app (flavor, version) / API; role (doctor, admin, patient, college, coach) | infer from the steps if clear (say so), else ask |

Ask for everything missing in **one** AskUserQuestion round. If reproduction steps or expected behaviour are still missing after that round, stop: say exactly what is missing and that `/nt-dev-coding:bug` can be run again with it. Save nothing in that case.

If the report contains anything that looks like a real username, password, phone, email, patient name or token, ask the user to replace it with a placeholder before saving; never store it.

## 2. Pick the id and save the report

Run `devtask.py id "<title>"` (pass the title, or a ticket id the user named, not the whole report: error codes such as `HTTP-500` are not ticket ids). If `id_source` is `ticket-in-text`, confirm it with the user. If the folder exists, ask: re-plan it (see "Existing id"), use `<id>-2`, or cancel.

## 3. Spec gate

Extract 3–8 terms from the steps (screen names, button labels, API paths, error text, module names; vocabulary from `<docs>/module-index.md`) and run `devtask.py specs <terms...>`. If `gate` is `stop`, **stop**: no impact report or module analysis covers this area; suggest `/nt-documentation:analyze <repo> <module>` for the matched module (or `/nt-documentation:impact "<bug summary>"`).

Then `mkdir -p <docs>/dev/<id>` and write `bug.md`: front-matter (`generated_by: nt-dev-coding/bug`, `generated_at` from `date`, `task_id`, `kind: bug`) followed by the report **verbatim**, then a "Clarifications" list with the user's answers.

## 4. Delegate to change-planner

Start the **nt-dev-coding:change-planner** agent with a prompt that begins:

```
plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>
docs_dir=<expanded docs dir>
task_dir=<docs_dir>/dev/<id>
kind=bug
mode=new
```

followed by the path of bug.md and the full JSON from `devtask.py specs`. Tell it to start from the reproduction steps, trace that exact path through the code, give the suspected root cause as `file:line` with reasoning (two candidates if it cannot decide, with how to tell them apart), then plan the **minimal** fix. AC-1 must be "the reproduction steps no longer reproduce the bug".

## 5. Verify, resolve §9, present and stop

Follow the `task` skill's steps 4–6 exactly (verification with one send-back, no approval while "Needs your decision" is open, the exact approval sentence, near-miss handling, and the approval-turn rule). Additionally check that ticket.md has the reproduction steps and the suspected root cause, and show the root cause (file:line, confidence, alternatives) first when presenting. Suggest `fix/<id>` as the branch name.
