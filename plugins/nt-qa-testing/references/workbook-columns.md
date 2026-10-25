# Workbook columns (NT_Web_QA_Sanity_Suite)

`report` builds `results.csv` with exactly these columns, in this order. Edit the list below to match the sheet header; one column per line, as a `- ` bullet, exact header text. `scripts/results_csv.py` reads only the bullets in the **Columns** section.

## Columns

- Test Case ID
- Module
- Sub-module
- Test Scenario
- Preconditions
- Test Steps
- Test Data
- Expected Result
- Actual Result
- Status
- Priority
- Remarks

## How each column is filled

`results_csv.py` matches a header to a case field by normalised name (lowercase, letters and digits only), so `Test Case ID`, `test_case_id` and `TestCaseID` all map to `id`. A header with no known field is written empty and reported as a warning.

| Field | Accepted header names | Source |
|---|---|---|
| `id` | Test Case ID, TC ID, Case ID | `cases.md` case id (`TC-<run-id>-NN`) |
| `module` | Module | plan scope |
| `sub_module` | Sub-module, Submodule, Screen | case's screen / sub-area |
| `scenario` | Test Scenario, Scenario, Title | case title |
| `preconditions` | Preconditions, Pre-conditions | case preconditions (roles by placeholder only) |
| `steps` | Test Steps, Steps | numbered steps joined by newlines |
| `test_data` | Test Data, Data | dummy data only |
| `expected` | Expected Result, Expected | case expected result |
| `actual` | Actual Result, Actual | result-checker's observed result |
| `status` | Status, Result | Pass / Fail / Blocked / Skipped |
| `priority` | Priority | P1 / P2 / P3 |
| `remarks` | Remarks, Comments, Notes | skip rule, bug id, evidence path, mismatch note |
| `bug_id` | Bug ID, Defect ID | bug id for `[bug-repro]` cases |
| `run_date` | Execution Date, Date, Run Date | run date (YYYY-MM-DD) |
| `environment` | Environment, Env | `web-staging` |
| `evidence` | Evidence, Screenshot | first screenshot path of the case |
