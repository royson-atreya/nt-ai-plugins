---
name: review
description: This skill should be used when the user asks to "review <id>", "show me the diff for <id>", "is the change for <id> safe", "re-review after fixes", or runs /nt-dev-coding:review. Writes nt-docs/dev/<id>/diff.md (every added/removed line grouped by file, with +/- counts and unplanned/pre-existing/mixed flags) and has the read-only code-reviewer agent, in a fresh context, review it for bugs, security problems and side effects on other modules and API consumers (via nt-documentation link-apis), saved as review.md. Nothing cosmetic. Never edits code.
argument-hint: "[id]"
disable-model-invocation: true
allowed-tools: Read, Glob, Write, Bash(python3:*), Bash(mv:*), Bash(date:*), Bash(cat:*), Bash(ls:*), Agent, Task, AskUserQuestion
---

# review: diff.md and an independent review.md

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` first. `<docs>` is `$NT_DOCS_DIR` or `~/atreya-ai/nt-docs`; `<task_dir>` is `<docs>/dev/<id>` as an absolute path. Never edit code in this skill.

## 1. Resolve the task

The argument is the id; without one use `cat <docs>/dev/ACTIVE` and say which. If that is empty, `ls -t <docs>/dev` and ask. If `<task_dir>/implement.md` does not exist, say implement has not run and suggest `/nt-dev-coding:implement <id>`; continue only if the user says the changes were made by hand.

## 2. Diff

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/diffstat.py" <id>
```

It writes `diff.md` and prints a JSON summary. Keep its `diff_sha256`: it identifies exactly the change being reviewed. If `files_changed` is 0, stop: nothing to review. If `errors` is non-empty, show them and stop. Tell the user the totals (+/−, files), and list `unplanned`, `pre_existing`, `mixed` and `flags_needing_review` (secret or redacted lines) before the review starts.

If `<docs>/api-links/api-links.json` is missing, warn that cross-module effects can only be checked from code, and suggest `/nt-documentation:link-apis`.

## 3. Independent review

If `<task_dir>/review.md` already exists, run `date +%Y%m%d-%H%M` and move it aside: `mv "<task_dir>/review.md" "<task_dir>/review-<ts>.md"`. That file is the previous review.

Start the **nt-dev-coding:code-reviewer** agent in a fresh context with a prompt that contains only:

```
plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>
docs_dir=<expanded docs dir>
task_dir=<task_dir>
task_id=<id>
previous_review=<absolute path of review-<ts>.md, or none>
Review the change for task <id>. Return the complete review.md document.
```

Do not pass your own opinion of the change, implementer notes, or a summary: the reviewer must judge from the files.

The agent has no write tools; it returns the document. Write it verbatim to `<task_dir>/review.md`, adding one line as the last front-matter field: `reviewed_diff_sha256: <diff_sha256 from step 2>` (replace any value the agent wrote). handoff uses it to detect code changed after review, so never omit it.

If the reply does not start with front-matter containing `verdict:`, start the agent again once with the same prompt plus "Your previous reply was not in the review.md format; return only the document, front-matter first." If that also fails, move the previous review back (if any), tell the user the review failed, and stop.

## 4. Report

Tell the user the verdict and the counts by severity, every P1 and P2 finding in one line (id, location, problem), any consumers marked not compatible, and acceptance criteria not covered.

- `CHANGES REQUIRED`: offer `/nt-dev-coding:implement <id> fix R-01 R-02 …` for the P1/P2 ids (the user decides which), then review again.
- Unplanned real changes: they need a re-plan (`/nt-dev-coding:task <id>`, works for bugs too) and `approve <id>`, or the user reverts them.
- `APPROVE` / `APPROVE WITH RISKS`: suggest `/nt-dev-coding:handoff <id>`.
