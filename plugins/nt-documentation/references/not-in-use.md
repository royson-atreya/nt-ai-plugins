# Not in use

Code that exists but is not live. Skills must label these as unused and must not describe them as live behaviour. Impact analysis must leave them out of estimates unless the change request names them.

Each entry lists the user's statement first, then what the code shows. Where the two differ, the entry says so. Resolve it before relying on it.

## Receptionist feature

- **Status (user):** not in use.
- **Code (web):** `app/Http/Controllers/ReceptionistController.php`; `resources/views/receptionist/{add,edit,view}-receptionist.blade.php`, `set-permission.blade.php`; `public/js/reception/receptionlist.js`; `public/css/nt_v2/reception/receptionlist.css`; routes in `routes/web.php`
- **Code (backend):** `app/Http/Controllers/ReceptionManagementController.php`.
- **`/reception-api/*` routes:**
  - **Exist in backend code:** yes, 33 routes (`laravel_routes.py backend --grep reception-api`): report 10, appointment 10, patient 5, prakruti 4, patientList 1, infinitePatientList 1, and others. They are spread across `MedicalReportSaveController`, `PatientDetailsController`, `AppointmentController` and others.
  - **Called by web/app:** no. All 33 appear in `api-links.json` → `orphan_routes`, and no web or app code mentions `reception-api`.
  - **Status: present but unused by web/app.** A client outside these three repos could still use them.
  - Checked against backend `8dfbb37db`, web `e8a9742b9`, app `0b7deec6d`.
- **Still referenced from live screens:** `doctor_dashboard/dashboard.blade.php`, `layouts/dashboard_nav_layout.blade.php`, the appointment and patient views. Treat these as dead branches or hidden menu items. TODO: verify how it is hidden (feature flag, role, or commented out).

## Research dashboard

- **Status (user):** only an external link from NT. It is not part of the NT product surface.
- **Research dashboard API:**
  - **Exists in backend code:** yes, 62 routes in the `researchDashboard` group (`routes/api.php:586`) and the `public/research-dashboard` group (`:909`), served by `app/Http/Controllers/ResearchDashboard/*` and `ResearchDasbhoardController.php`.
  - **Called by web:** yes. All 62 routes have web callers: 64 call sites, all in the web app's `app/Http/Controllers/ResearchDashboardController.php` (e.g. `:90` → `POST /researchDashboard/getAllRules`, backend `routes/api.php:593`).
    - The web side is a set of research pages behind `/researchLogin` and the `check_research_auth_token` middleware (`routes/web.php:78, 175`), with views in `resources/views/research_dashboard/` and `researchDashboardPages/`.
  - **Called by app:** no.
  - Checked against backend `8dfbb37db`, web `e8a9742b9`, app `0b7deec6d`.
- **Rule for now:** document it only as an external box on diagrams. Do not analyse it as an NT module. This rule rests on the user's statement. Because the web app does call this API, `link-apis` and `diagram` will show it as linked from web.

## TestPurpose controller

- **Status (user):** test-only and not in use.
- **Code (backend):** `app/Http/Controllers/TestPurpose/S3BucketController.php`, which is still registered in `routes/api.php`. Note this as a risk (an exposed test endpoint) in impact reports touching S3. Do not document it as a feature.

## Stub (add more)

<!-- Add entries in the same format: Status (user) / Code / Rule. -->
