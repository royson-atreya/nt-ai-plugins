# QA scope rules

`plan` and `cases` apply every rule below. When a rule removes a case, keep the case in `cases.md` with status **Skipped** and cite the rule id (e.g. `Skipped (R2)`), so the workbook shows it was considered, not forgotten.

| Id | Rule | What to do |
|---|---|---|
| R1 | **Medical Assessment, Nadi Capture** is a manual device process. | Skip its success-flow cases. Test only the screens and validation around it (entry screen, required fields, error messages, navigation, cancel/back). |
| R2 | **No real OTP.** | Skip any case that needs a real WhatsApp, email or SMS OTP code. Screens before the OTP step (request form, validation, resend button state) are in scope. |
| R3 | **Reports.** | Test only report generation and language selection. Do not verify clinical content of a report. |
| R4 | **NT Mitra chatbot.** | Basic level only: opens, accepts a simple question, shows a reply, closes. No conversation-quality or medical-answer checks. |
| R5 | **Languages in scope:** English, Marathi, Hindi, Czech, German, Spanish, Italian. | Language cases use only these. Any other language is out of scope. |
| R6 | **Staging only.** | Run only on `https://staging-dashboard.naditarangini.com` (API `staging-api.ashoka.world`). Production (`https://dashboard.naditarangini.com`, `naditarangini.com`, `www.naditarangini.com`, `api.ashoka.world`) is blocked by a hook and must never be targeted. |
| R7 | **Test accounts** (doctor, admin, patient, college) come from the plugin's user config. | Refer to them only by role and placeholder (`{{nt-qa:doctor:username}}`, `{{nt-qa:doctor:password}}`). Never write a username or password into any plugin file, plan, case, report or CSV. If a role is not configured, its cases stay `Ready` in cases.md and are reported **Blocked** at run time; never run them with another account. |

## Where the rules bite (web module ids from `Nadi-Tarangini-Frontend/module-map.json`)

| Rule | Modules |
|---|---|
| R1 | `medical-assessment`, `live-nadi-capture`, `external-nadi-capture` |
| R2 | `auth-login-signup` (WhatsApp/email OTP login, forgot password), any sign-up or verification step |
| R3 | `visit-reports` (backend `core-reports`, `core-reports-wellness`) |
| R4 | `help-notifications` (NT chatbot widget) |
| R5 | `shared-localization` and any screen with a language selector |
| — | Modules with status `not-in-use` (e.g. `receptionist`, `research-dashboard`) are out of scope unless the user names them explicitly; say so in the plan. |

## Also always

- Dummy test data only (see `conventions.md` → Test data). Never real patient data.
- Test only the given task, bug or module. Neighbouring features appear only as regression checks named in the spec's knock-on/impact section.
