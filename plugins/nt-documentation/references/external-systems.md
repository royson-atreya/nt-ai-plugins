# External systems

Systems outside the three repos that NT code talks to. Pointers come from a read-only scan at backend `8dfbb37db`, web `e8a9742b9`, app `0b7deec6d`. Config entries list **key names only**. Values live in `.env`, which must never be read.

Use this file to label external boxes in diagrams and to flag cross-system impact.

## AWS Lambda / API Gateway (report and plan generators)

Backend calls hosted Lambda functions over HTTP to compute nadi analysis results and generate reports and plans.

- Config (`backend/config/services.php`): `swasthyadarshika.url` (`SWASTHYADARSHIKA_URL`), `dos_and_donts.url`, `weekly_diet.url`, `rutucharya.url`, `yoga.url` (`YOGA_PLANNER_URL`), `translation.url`
- Callers: `app/Services/NpVikrutiLambdaService.php`, `app/Services/NadiTaranginiV3.php`, `app/Services/GenerateAarogyaDarshika.php`, `app/Services/External/GenerateSwasthyaData.php`, `app/Services/External/GenerateReportResponseJson.php`, `app/Services/TuryaaDietService*.php`, `app/Services/yogaReportService.php`, `app/Services/SpaReportService.php`, `app/Services/patanjaliReport.php`, `app/Services/OnePagerNtReportService.php`, `app/Services/NTUser/{DietMangementService,YogaPlannerService}.php`, `app/Http/Controllers/GenerateSwasthyaLambda.php`
- Logged in: `app/Models/NadiParikshaModels/NpExternalServiceLogs.php`
- TODO: verify the full list of Lambda functions and which ones are still live.

## AWS S3

- Report PDFs, profile pictures and translations. Backend: `app/Services/S3BucketService` (graph hub). Web: `app/Services/S3TranslationService.php`, `S3TranslationLoader`. App reads public S3 URLs directly (e.g. `lib/doctor_dashboard/visit_reports/view/visit_report_list_screen.dart`).

## Samvit Chakra

- Separate system with a payment bridge, plus a DB connection `samvit_chakra_db` defined in the backend (see "Second (and third) database" below for its status).
- Backend: `app/Http/Controllers/SubscriptionController.php`, `SignUpController.php`, `LinkDeviceContoller.php`, `config/app.php`
- Web: `app/Http/Controllers/SamvitPaymentBridgeController.php`, `resources/views/payments/samvit_checkout*.blade.php`, `routes/web.php`, `routes/api.php`
- TODO: verify what Samvit Chakra is (product or partner) and the direction of each data flow.

## Interakt (WhatsApp and SMS)

- Config: `interakt`, `interaktsms` (`INTERAKT_AUTH_BASIC`, `INTERAKT_API_URL`)
- Backend: `app/Services/OtpSmsService.php`, `app/Services/NpOtpSmsService.php`, `app/Services/EmailService.php`, `app/Services/turyaaDownloadService.php`, `app/Http/Controllers/SmsController.php`, `app/Repositories/NTAdmin/Eloquent/NotificationRepository.php`
- Also present: `sms` block (`BULK24SMS_*`, another SMS provider). TODO: verify whether it is still used.

## ZeptoMail (transactional email)

- Config: `zeptomail` (`send_email_url`), plus a reference in `config/app.php`
- Backend: `app/Services/EmailService.php`, `app/Services/NpEmailService.php`, `app/Services/AshokaDashboardService.php`, `app/Http/Controllers/SubscriptionController.php`, `app/Http/Controllers/SmsController.php`
- Mailgun, Postmark and SES blocks also exist in `config/services.php` (Laravel defaults). TODO: verify that only ZeptoMail is live.

## Razorpay (payments)

- Config: backend `razorpay` (`key`, `secret`, `webhook_secret`, `nt_webhook_secret`); web `razorpay`
- Backend: `app/Http/Controllers/NadiPariksha/NPPaymentController.php`, `NpPaymentControllerV2.php`, `app/Http/Controllers/NtTransactionController.php`, `app/Services/NpCommonService.php`, webhook routes in `routes/api.php`
- Web: `SamvitPaymentBridgeController.php`, `AdminDashboardController.php`, `resources/views/subscription/checkout.blade.php`, CSRF exemption in `app/Http/Middleware/VerifyCsrfToken.php`
- App: `lib/doctor_dashboard/subscription/utils/launch_payment.dart`. `razorpay_flutter` is commented out in `pubspec.yaml`, so check how the app launches payment.

## ENACH (recurring debit mandates)

- Backend: `app/Http/Controllers/ENACH/ENACHController.php`; models `EnachCustomers`, `EnachMandate`, `EnachDebitLog`; routes in `routes/api.php`
- Provider config: probably the `worldline` block (`merchant_id`, `scheme_code`). TODO: verify.

## Second (and third) database

- `mysql`: the main DB
- `turyaa_db` (`DB_*_SECOND` env keys, displayed as turyaa_v1_db): 44 models set `$connection = 'turyaa_db'`, mostly under `app/Models/TuryaaModels/`
- `samvit_chakra_db` (`DB_*_THIRD`):
  - **Exists in backend code:** yes, but only as a connection definition in `config/database.php:102`. No model sets `$connection = 'samvit_chakra_db'`, and nothing in `app/`, `routes/` or `database/` references it.
  - **Called by web/app:** no. No link in `api-links.json` touches a `samvit_chakra_db` table, and no web or app code mentions it.
  - **Status: present but unused by web/app.** It also appears unused by the backend itself. Samvit Chakra is reached over HTTP (above), not through this connection.
  - Checked against backend `8dfbb37db`, web `e8a9742b9`, app `0b7deec6d`.
- When mapping tables, always record which connection a model uses.

## Bluetooth nadi device

- App: `flutter_blue_plus` (`pubspec.yaml`). Main flow in `lib/doctor_dashboard/nadi_flow_new/`: `controller/choose_device/choose_device_bloc.dart`, `controller/live_nadi1/live_nadi1_bloc.dart`, `view/live_nadi_screen1.dart`
- Web: browser Bluetooth/USB (Web Serial) capture in `public/js/live_nadi/nadi.js`, `public/js/nt_lite/nt_lite_live_nadi_usb.js`, `public/js/external/live_nadi/nadi.js`
- Backend: device registry `app/Models/PgDeviceList.php`, `app/Http/Controllers/Admin/DeviceManagementController.php`, `LinkDeviceContoller.php`; there is also a browser BLE script at `public/js/nadiPariksha/livenadiBluetooth.js`
- TODO: verify the device protocol doc and the firmware owner.

## Others seen (not yet classified)

- Firebase (Auth and Messaging) in the app and backend (`NpFirebaseNotificationService`)
- Google OAuth (`google` block), ipinfo (`ipinfo`)
- External partner webhooks: `app/Services/ExternalWebhookService`, `app/Jobs/External/SendExternalWebhookJob.php`
- Chatbot proxy in web: `NtChatbotProxyController`, `chatbot` config
- TODO: verify and move each one into its own section.
