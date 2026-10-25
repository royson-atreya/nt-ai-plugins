# nt-qa-testing

Spec-driven QA for **one** Nadi Tarangini task, bug or module on **web staging**. Test cases are built from the verified specs that `nt-documentation` writes to `~/atreya-ai/nt-docs` (module analyses, impact reports, journeys, API links, module maps), never from the code. The plugin never writes product code and never touches `~/atreya-ai/repos`.

## Install

```
/plugin marketplace add ~/atreya-ai/nt-ai-plugins
/plugin install nt-qa-testing@nt-ai-plugins
```

Claude Code then asks for the staging URL and the test accounts (see Configuration). For local development: `claude --plugin-dir plugins/nt-qa-testing`.

## Commands

| Command | What it does |
|---|---|
| `/nt-qa-testing:plan <task\|bug\|module>` | Reads the nt-docs spec/impact (or your bug report); lists what to test, why, and which screens/APIs are in scope → `plan.md` |
| `/nt-qa-testing:cases [run-id]` | Numbered test cases (preconditions, steps, dummy data, expected result); bug repro cases first → `cases.md` |
| `/nt-qa-testing:run-web [run-id]` | Runs the cases on staging with Playwright, screenshot per step, then an independent evidence check → `run.json`, `check.md` |
| `/nt-qa-testing:report [run-id]` | Pass/fail summary with evidence + workbook rows → `report.md`, `results.csv` |
| `/nt-qa-testing:retest <bug-id>` | Re-runs only the bug's `[bug-repro]` cases and says **fixed / not fixed** |

Typical flow: `plan` → review `plan.md` → `cases` → review `cases.md` → `run-web` → look at mismatches → `report`.

## Output

```
~/atreya-ai/nt-docs/qa/<task-or-bug-id>/
  bug.md  plan.md  cases.md  screenshots/  run.json  check.md  check.json  report.md  results.csv
  retest-<timestamp>/    # one per retest (retest.md = FIXED / NOT FIXED / INCONCLUSIVE)
  rerun-<timestamp>/     # run-web on a subset of cases; the main run's evidence is untouched
  previous-<timestamp>/  # an earlier full run, moved aside when you chose overwrite
```

## Prerequisites

- The **playwright** plugin (`mcp__plugin_playwright_playwright__*` tools) installed and connected.
- `python3` (3.9+) for the hooks and the CSV script.
- nt-documentation specs for the area under test. If none exist, `plan` stops and suggests `/nt-documentation:analyze web <module>` or `/nt-documentation:impact`. Bugs can run without a spec: your reproduction steps and expected behaviour are the spec.

## Configuration

Asked when the plugin is enabled; change later with `/plugin` → Installed → nt-qa-testing → **Configure options**. Nothing is written to this repo.

| Option | Notes |
|---|---|
| `staging_base_url` | default `https://staging-dashboard.naditarangini.com` |
| `doctor_username` / `doctor_password` | sensitive (secure storage) |
| `admin_username` / `admin_password` | sensitive |
| `patient_username` / `patient_password` | sensitive |
| `college_username` / `college_password` | sensitive |

Leave a role empty if you have no account for it; its cases stay Ready in `cases.md` and are reported **Blocked** at run time, so adding the account later unblocks them without regenerating cases.

Edit `references/workbook-columns.md` so its column list matches your NT_Web_QA_Sanity_Suite header exactly; `report` follows it.

## Scope rules

See `references/qa-scope-rules.md` (Nadi Capture success flow skipped, no real OTP, reports = generation + language only, NT Mitra basic only, 7 languages, staging only, credentials from config only).

## Safety hooks

| Hook | Behaviour |
|---|---|
| `guard.py` (PreToolUse) | **Everywhere:** blocks production hosts: any `*.naditarangini.com` / `*.ashoka.world` that is not a staging host (incl. `naditarangini.com`, `www.`, `dashboard.`, `api.ashoka.world`) in Playwright inputs, WebFetch and network commands in Bash. **Inside `~/atreya-ai`:** Playwright may open only `staging-dashboard.naditarangini.com` / `staging-api.ashoka.world` (and `about:blank`); no `file:`/`javascript:` URLs; `browser_evaluate` / `browser_run_code_unsafe` disabled; only `browser_take_screenshot` may save a file; no `git commit/push/pull`; no reading `.env*`, `*.jks`, `*.keystore`, `firebase-*.json`, `google-services.json`, `GoogleService-Info.plist` via Read, Grep, Glob or Bash; nothing writes into `~/atreya-ai/repos`, except Write/Edit for an nt-dev-coding task the user approved (`approve <id>`), in a repo named in its plan, on a non-protected branch (shared rule in `hooks/devgate.py`, 0.1.1). Claude can never write the approval markers. |
| `creds.py pre` (PreToolUse) | Only in sessions started under `~/atreya-ai`: in `browser_type` / `browser_fill_form`, replaces `{{nt-qa:<role>:username\|password}}` with the real value from secure config. Placeholders in any other browser tool, unknown roles and unconfigured roles are refused. Any Write/Edit/Bash input containing a real configured credential is refused. |
| `creds.py post` (PostToolUse) | Masks every configured credential (incl. JSON-, URL- and base64/Basic-auth-encoded forms) as `●●●●` in Playwright, Read, Bash and Grep output before Claude sees it. |
| `session_banner.py` (SessionStart) | Under `~/atreya-ai`: lists the commands, the staging URL and which roles are configured (yes/no only). |

Run `bash tests/test_guard.sh` after changing a hook or `results_csv.py` (101 checks, fake credentials only).

`run-web` and `retest` create records on staging, so they run only when you type the command (`disable-model-invocation`); `plan`, `cases` and `report` also respond to plain requests.

**Limits, stated plainly**

- Hooks see tool calls, not the page's own network traffic. If staging itself loaded something from a production host, no hook could stop it; web-runner therefore checks the page URL after every step and aborts the run if it leaves staging.
- Start Claude Code from `~/atreya-ai` for QA runs: credentials are injected only there, where the browser guards apply.
- Screenshots are images and are not masked. Password fields show dots; web-runner screenshots a login only after submitting it (or only the error message if it fails), but a username can still appear on a page that displays it.
- Hooks fail open if `python3` is missing or a hook times out (10 s): Claude Code then runs the tool unguarded and unmasked. Keep `python3` on PATH.
- Masking changes what Claude sees. If you enable OpenTelemetry export for Claude Code, its tool spans record the original tool output.
- Use distinctive test usernames (e.g. `qa.doctor+01@…`): masking and the write check match whole values, and a plain word such as `doctor` would not be checked in written files.
- Reading the product repos is not blocked by this plugin (nt-documentation needs it); the skills forbid using code to design or judge tests.

## Roadmap (v2)

- Mobile app testing via **LambdaTest MCP** (real devices).
- Zoho Sprints: attach results to the bug/task.
- Memory of past runs and flaky cases.
