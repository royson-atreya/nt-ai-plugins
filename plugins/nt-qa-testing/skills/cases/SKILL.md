---
name: cases
description: This skill should be used when the user asks to "write test cases", "create the cases for <run>", "generate test cases from the plan", "add validation cases", "redo the cases", or runs /nt-qa-testing:cases. Writes numbered Nadi Tarangini web test cases (preconditions, steps, dummy test data, expected results) for the scope in an approved qa/<run-id>/plan.md, with a bug's reproduction steps first, by delegating to the test-designer agent.
argument-hint: "[run-id] [change request for a revision]"
allowed-tools: Read, Glob, Bash(ls:*), Agent, Task, AskUserQuestion
---

# cases: numbered test cases for the planned scope

Produce `<docs>/qa/<run-id>/cases.md` in the exact format of `${CLAUDE_PLUGIN_ROOT}/references/conventions.md`, designed by the `test-designer` agent from the plan and its specs, never from code.

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` (cases.md format, run resolution) first. `<docs>` is `$NT_DOCS_DIR` or `~/atreya-ai/nt-docs`.

## 1. Resolve the run

- Resolve the run per conventions.md. If the first word is not a run folder, the whole argument is the change request.
- Require `plan.md` in it. If missing, stop and suggest `/nt-qa-testing:plan <item>`.
- Read `plan.md`. If any open question is tagged `[blocking]`, list them and ask whether to proceed.
- If `cases.md` already exists and no revision request was given, ask: revise (pass the user's change), regenerate from scratch, or keep.

## 2. Configured roles

Take the configured roles from the session context line "Test roles configured: …" (SessionStart banner); if absent, pass `configured_roles=unknown`. This is informational: cases for unconfigured roles stay `Ready` and web-runner reports them Blocked at run time, so adding the account later unblocks them. If the banner says `none`, warn the user that every case will be Blocked until accounts are configured (/plugin → Installed → nt-qa-testing → Configure options).

## 3. Delegate to test-designer

Start the `nt-qa-testing:test-designer` agent. The prompt begins with:

```
plugin_root=<expanded ${CLAUDE_PLUGIN_ROOT}>
docs_dir=<absolute docs dir>
run_dir=<absolute qa/<run-id> path>
kind=<task|bug|module from plan.md front-matter>
configured_roles=<doctor,admin,... | unknown>
```

followed by the task: "Write cases.md for this run following conventions.md and qa-scope-rules.md." For a revision, add the user's change request verbatim and "keep ids of unchanged cases".

## 4. Check the result

Read `cases.md` and verify quickly, fixing nothing yourself:

- front-matter present; ids sequential `TC-<run-id>-NN`; for a bug, `[bug-repro]` cases first;
- every case has Module, Sub-module, Priority, Role, Spec, Status, Preconditions, Test data, numbered `→ Expected:` steps, `Expected result:`;
- no real credentials (only `{{nt-qa:<role>:…}}` placeholders), no production URL, data uses `QA-AUTO` patterns.

If something is wrong, send the agent back once with the specific defects. If defects remain after that, list them in the hand-back; do not loop and do not edit the file yourself.

## 5. Hand back

Show the user: counts by status (Ready / Skipped with rule / Blocked) and priority, the bug-repro case ids, open questions, and the path. Ask them to review `cases.md` (edits by hand are fine if they keep the format) and then run `/nt-qa-testing:run-web <run-id>`. Do not start the run in the same turn.
