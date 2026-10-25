---
name: task
description: This skill should be used when the user asks to "plan this task", "write a ticket for <requirement>", "make a change plan for <feature>", "which files do I need to change for <requirement>", "re-plan <id>", or runs /nt-dev-coding:task. Turns ONE Nadi Tarangini requirement into ticket text (title, requirement, description, acceptance criteria) and a change plan (repos, files, functions, DB impact, API consumers, risks, estimate) from nt-docs specs, saves them to nt-docs/dev/<id>/, then stops for the user's approval. Also re-plans an existing task or bug id (keeping its kind). Never edits code. For a new defect with reproduction steps use the bug skill.
argument-hint: "<requirement text | path to a .md/.txt file> | <existing id> [what to change]"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Write, Bash(python3:*), Bash(mkdir:*), Bash(ls:*), Bash(date:*), Bash(cat:*), Agent, Task, AskUserQuestion
---

# task: ticket and change plan for one requirement (or a re-plan)

Produce `<docs>/dev/<id>/ticket.md` and `plan.md`, then **stop** for approval. Never edit anything in the product repos (`$NT_REPOS_DIR`, default `~/atreya-ai/repos`) from this skill.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` first. `<docs>` is `$NT_DOCS_DIR` or `~/atreya-ai/nt-docs`; if it does not exist, stop: "nt-docs not found; set NT_DOCS_DIR or run `/nt-documentation:map all` first".

## 1. New task or re-plan?

If the first argument word is a folder in `<docs>/dev/`, this is a **re-plan** of that id: go to step 1R. Otherwise continue with step 1N.

### 1N. New task: read the input

- A file path: read it. No argument: ask what to build.
- If the text is a defect report (steps to reproduce, expected/actual, "bug", "broken", "error"), suggest `/nt-dev-coding:bug` instead; continue only if the user insists.
- If the text contains what looks like a real phone, email, patient name, password or token, ask the user to replace it before anything is saved.
- When the requirement is ambiguous in a way that changes scope (which roles, web only or also the app, new API or extend existing), ask up to three questions with AskUserQuestion. Otherwise state your interpretation in one sentence and continue.
- Pick the id: `devtask.py id "<title or first line of the requirement>"`. If `id_source` is `ticket-in-text`, confirm the id with the user in one question (it may be an error code, not a ticket). If the folder already exists, ask: re-plan it (go to 1R), use `<id>-2`, or cancel.

### 1R. Re-plan: gather what changed

Run `devtask.py status <id>` and read the existing `ticket.md`, `plan.md`, and if present `bug.md`, the "Plan gaps" and "Deviations" in `implement.md`, and the findings and "Plan conformance" in `review.md`.

- **Keep the kind** from status (`task` or `bug`). For a bug, never rewrite `bug.md`; new information from the user is appended under its "Clarifications" list.
- The change request is the text after the id. If there is none, summarise the plan gaps / unplanned files / findings you found and ask the user what to change.
- Tell the user that a re-plan makes the current approval invalid until they type `approve <id>` again.

## 2. Spec gate

Extract 3–8 search terms (domain nouns, screen names, API URIs, table names, module ids; vocabulary from `<docs>/module-index.md`). Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/devtask.py" specs <term> <term> ... [--module backend:<id>]
```

Iterate on the terms once if the result is empty or clearly off-target. If `gate` is `stop`, **stop** without creating a folder: no impact report or module analysis covers this. List the modules that matched (map-only) and suggest `/nt-documentation:impact "<requirement>"` (or `/nt-documentation:analyze <repo> <module>` for one module). Do not plan without specs.

After the gate passes, `mkdir -p <docs>/dev/<id>` for a new task.

## 3. Delegate to change-planner

Start the **nt-dev-coding:change-planner** agent with a prompt that begins:

```
plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>
docs_dir=<expanded docs dir>
task_dir=<docs_dir>/dev/<id>
kind=<task, or the existing kind for a re-plan>
mode=new | re-plan
```

followed by, for a new task, the requirement text verbatim, your interpretation and the user's answers; for a re-plan, the change request, the plan gaps / deviations / review findings (copied), and the user's answers. Always append the full JSON from `devtask.py specs`.

## 4. Verify the plan

If the agent stopped without writing (it found the specs insufficient), tell the user its reason and stop.

Otherwise run `devtask.py status <id>` (exit 1 is expected: not approved yet) and check:

- `plan_repos` is non-empty and every repo exists under `$NT_REPOS_DIR`; `files_outside_repos` and `missing_files` are empty (new files must sit under a folder entry ending in `/`).
- plan.md starts with its front-matter (a re-plan "Revision" block goes after it); ticket.md has acceptance criteria; plan.md has sections 1–10 from conventions.md.

If anything fails, send the agent back once with the exact problems. If it still fails, show the problems to the user and stop **without** inviting approval.

## 5. Resolve "Needs your decision" (§9)

A plan is never offered for approval while §9 has an open item. If §9 lists open items, ask them with AskUserQuestion (never offer "approve" as an answer option), re-run the planner in re-plan mode with the answers so they are recorded in §9 as `Decision → Answer`, then repeat step 4. Repeat until §9 has no open items.

## 6. Present and stop

Show the user, concisely:

- ticket title, kind, requirement (one line), acceptance criteria,
- the change table (repo, file, function, change), DB impact, API consumers affected,
- top risks, estimate, and the §9 decisions with their answers,
- current branch per repo from `devtask.py status`; for master/main/production give the command the user can run, e.g. `git -C <repos dir>/<Repo> checkout -b feature/<id>`.

End with exactly: **"To approve, type `approve <id>` as the whole message. To change the plan, tell me what to change."** Then stop.

- Never start implement, never write APPROVED, and never treat "ok", "looks good", "approved" or "approve it please" as approval: only a prompt that is exactly `approve <id>` counts (a hook records it). If the user answers with a near-miss, repeat the exact form.
- On the turn after the hook records the approval, reply only that the next step is `/nt-dev-coding:implement <id>`. Never edit the repos outside the implement skill.
