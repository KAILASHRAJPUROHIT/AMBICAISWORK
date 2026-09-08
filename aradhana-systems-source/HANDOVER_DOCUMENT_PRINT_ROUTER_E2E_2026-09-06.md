# Aradhana Document Print + Ornate Router — End-to-End Handover

**Prepared:** 2026-09-06, Asia/Kolkata  
**Scope:** QR Print Server, document workflow, P355 document renderer, Ornate print router, Payment Notifier dashboard integration, PC2 production status.  
**Client name:** Aradhana Jewellers.  
**Design branding:** user-facing product surfaces use Aradhana; “Powered by AMBIC DIGITAL” belongs only in permitted splash/about/design locations.

---

## 1. Executive state — read this first

### What is working and verified

1. QR document queue / billing document flow exists in the QR Print Server source and has been pushed to its Render-connected repository.
2. QR Scanner has two intended actions:
   - **Send for Billing**: creates a held document bundle for a biller; it does not print automatically.
   - **Direct to Printer**: queues a QR print job; all QR-originated jobs are hardwalled to P355.
3. The P355 document renderer was tested with a dummy input. It generated a two-page PDF only and did not physically print during that test.
4. The revised P355 document layout was visually accepted for the tested single-card case:
   - ID-card mode caps cards at 6 cm wide × 4 cm high.
   - document content uses the lower half of the reverse page;
   - terms use the upper half, horizontally oriented where needed.
5. A local document-alert toast was seen on PC2. It is a non-blocking, top-right notification and includes document actions.
6. Two Ornate Voucher Print visual references were captured directly from PC2:
   - normal office sales format: `GST Sales Voucher (A4) Shree Aradhana`
   - URD / purchase format: `GST Purchase Voucher (A4) SHREE ARADHANA JEWELLERS`

### Current production state — PC2

The hybrid router was installed and verified at **2026-09-06 17:54 IST**:

```text
Process: AradhanaOrnateAutoPrint, PID 76536
EXE SHA-256: 8898BCA405D34604C158965F9BE8E82A8A3E413A3955C6D2336971AA991372DC
Office-format reference present: True
```

It must still pass controlled normal-Sales, second-copy, URD, and non-Ornate tests before being called production-accepted. Do not reboot PC2 until router startup has been verified through one restart.

Earlier NPAV removal events remain important release history. Future binaries must continue through the organisation’s normal security review process; do not create a broad AV folder exclusion as a system design.

### Important distinction

The QR/document workflow source and the new router source are **not the same thing as a successful PC2 deployment**. A source change, a staged package, or an “Installed and started” batch message is not proof. The proof standard is:

1. EXE exists at the installed path.
2. EXE process is running under the signed-in biller session.
3. companion office-format reference exists.
4. a controlled normal bill and a controlled URD bill create the expected logs and destinations.

---

## 2. Goals and hard business rules

### Print-copy routing

| Job / copy | Required destination |
|---|---|
| Normal office bill first copy | HP LaserJet P1007 |
| Normal customer bill second copy | P355 route (`355 Letterhead Capture` → physical HP Laser MFP 355sdnw) |
| URD / purchase voucher | P355 |
| Third or later copy | P355 |
| QR Scanner direct document print | P355 |
| QR document selected by biller for standalone document print | P355 only; never touches the bill |

### Safety principles

- P1007 is the restricted printer because it carries pre-printed letterhead stock.
- No timing-only logic may decide that a job belongs on P1007.
- Unknown format, failed capture, missing reference, missing document service, or missing scanner response must fail safely to P355 or retain normal bill flow—not send to P1007.
- A document popup must never block a biller from printing a bill. Ignoring / dismissing it keeps normal routing.
- A document must not print automatically merely because it was uploaded.
- Secrets must not appear in config files, command lines, screenshots, source control, or handover documents.

---

## 3. Machine roles and network model

| Machine | Intended role | Notes |
|---|---|---|
| Home laptop (`192.168.0.12`) | development, Payment Notifier dashboard/backend, future OTA control server | production dashboard previously used port 8000 backend and port 5173 frontend |
| PC2 / Billing PC | primary biller and P1007 physical attachment | normal-user tray router; document workflow API on loopback port 8310; current router missing after NPAV removal |
| Dell / Server | related relay / server role | do not assume it has PC2’s physical printers; separate deploy verification required |
| QR Print Server | cloud-hosted scanner UI and held document queue | QR service deployed from `qr-print-server` Render-connected repository |

Network constraint: intended normal operations remain LAN/Wi-Fi constrained where applicable. QR Scanner cloud connection is a separate external service path and must use its authenticated bridge endpoint for biller document bundles.

---

## 4. Source-of-truth locations

### Repositories and projects

```text
C:\AradhanaSystems\projects\print-router
C:\AradhanaSystems\projects\qr-print-server
C:\AradhanaSystems\platform\plugins\document-print-workflow
C:\AradhanaSystems\projects\payment-auditor
C:\AradhanaSystems\platform\ota-control
```

### PC2 runtime locations

```text
C:\ProgramData\Aradhana\OrnateAutoPrintTray\
C:\PrintBridge\
C:\AradhanaSystems\platform\plugins\document-print-workflow\
C:\PrintBridge\document_bundles\
C:\PrintBridge\document_decisions\
C:\PrintBridge\routing_diagnostics\
```

### Key router files

```text
C:\AradhanaSystems\projects\print-router\src\AradhanaOrnateAutoPrint.cs
C:\AradhanaSystems\projects\print-router\build-and-install\Build_Aradhana_Ornate_AutoPrint.bat
C:\AradhanaSystems\projects\print-router\build-and-install\Install_Aradhana_Ornate_AutoPrint.bat
C:\AradhanaSystems\projects\print-router\assets\office-sales-voucher-format-reference.png
C:\ProgramData\Aradhana\OrnateAutoPrintTray\OrnateAutoPrint.log
C:\ProgramData\Aradhana\OrnateAutoPrintTray\config.txt
```

### Key document workflow files

```text
C:\AradhanaSystems\platform\plugins\document-print-workflow\service\app.py
C:\AradhanaSystems\platform\plugins\document-print-workflow\bridge\qr_bundle_sync.py
C:\AradhanaSystems\platform\plugins\document-print-workflow\bridge\biller_popup.py
C:\AradhanaSystems\platform\plugins\document-print-workflow\bridge\document_alert_notifier.py
C:\AradhanaSystems\platform\plugins\document-print-workflow\bridge\cache_bundle.py
C:\AradhanaSystems\platform\plugins\document-print-workflow\bridge\queue_standalone.py
C:\AradhanaSystems\platform\plugins\document-print-workflow\renderer\p355_document_renderer.py
```

### QR Print Server files

```text
C:\AradhanaSystems\projects\qr-print-server\cloud-server\app.py
C:\AradhanaSystems\projects\qr-print-server\cloud-server\templates\upload.html
```

### Payment Notifier dashboard integration files

```text
C:\AradhanaSystems\projects\payment-auditor\backend\review_api.py
C:\AradhanaSystems\projects\payment-auditor\frontend\src\api\client.ts
C:\AradhanaSystems\projects\payment-auditor\frontend\src\pages\BankActivityPage.tsx
C:\AradhanaSystems\projects\payment-auditor\scripts\aradhana_service_control.ps1
```

---

## 5. QR Scanner / QR Print Server design

### User flow

1. Staff scans Aadhaar, PAN, bank proof, or another customer document at the QR Print Server.
2. The scanner UI defaults to **ID card** mode. Full-page mode remains available.
3. Staff chooses one of two explicit actions:
   - **Send for Billing**: hold in the biller queue.
   - **Direct to Printer**: enqueue as a QR print job for P355.
4. Neither action auto-attaches to a bill.

### Held billing bundles

Each held bundle has a bundle ID, timestamps, source file list, print mode, document count, OCR linkage, and a display/customer label.

Expected lifecycle:

```text
pending → biller attaches / biller prints documents / expires after 30 minutes
```

Required expiry rule:

- If a bundle remains pending for 30 minutes and no biller chooses Attach or Print documents, it is removed from the active biller queue.
- Historical/audit data remains available under the 365-day QR document archive policy; “removed from queue” is not “erase all audit history.”

### Cloud implementation status

The QR repository received and pushed commit:

```text
969efaf Finalize billing queue and document actions
```

Implemented behavior includes:

- 30-minute pending-bundle expiry;
- bridge-authenticated document dashboard endpoint;
- 365-day document list;
- authenticated individual document download endpoint;
- `reprint` action that queues archived documents without changing original history;
- `resend-to-biller` action that creates a fresh current pending bundle;
- direct print / billing queue UI paths;
- hardwall of QR print configuration to the required P355 destination.

Repository caution: do not stage unrelated top-level deleted/disabled files in the QR repository. Its known unrelated dirty state included old disabled artifacts and an `_merged_from_Aradhana_Projects_copy` directory.

---

## 6. OCR design and status

### Intended OCR chain

```text
QR scan
  → QR cloud stores document + creates isolated OCR work item
  → local Payment Notifier OCR consumer/poller receives work
  → local OCR extracts candidate fields/name
  → QR bundle display label can be refined to “<name> — OCR name, verify”
  → document tab displays OCR fields for review/copy
```

### Rules

- OCR is an aid only. It does not prove identity or automatically establish a customer/bill relationship.
- Biller must choose the correct document bundle before Attach.
- The customer name shown in popup/dashboard is a display label and must retain verification language where OCR supplied it.
- QR document payloads are not sent to a new external OCR service by this router work.

### Current known state

- One old/real document reached the dashboard and showed an OCR-derived name (`KAILASH RAJPUROHIT`) in the Bank Activity KYC section.
- OCR did not appear in every observed popup run. This must be retested after the document queue and dashboard integration are both deployed/restarted.
- PC2 does not have Tesseract installed. This only affected the temporary Voucher Print calibration script. The intended QR/KYC OCR chain is separate from Tesseract.

---

## 7. Local Document Workflow API on PC2

### Service

```text
URL: http://127.0.0.1:8310
Health: http://127.0.0.1:8310/health
```

The API is a local Flask service. Its job is to track held bundle state, selected decisions, and local waiting sessions for the biller flow.

### Python/runtime dependency discovered on PC2

PC2 uses:

```text
C:\Users\Lenovo\AppData\Local\Programs\Python\Python313\python.exe
```

Flask was initially missing. After installing it, the following health response was observed:

```json
{"pending_bundles":0,"status":"healthy","waiting_sessions":0}
```

### Persistence status

The task `AISDocumentWorkflowApi` was previously installed during testing but later could not be found after restart / endpoint-security disruption. The service was manually launched successfully during tests. Therefore **do not claim it is persistent today** until all are true:

1. Scheduled task exists.
2. Scheduled task starts after PC2 reboot.
3. `http://127.0.0.1:8310/health` returns HTTP 200 after reboot.
4. NPAV permits the chosen service host/runtime.

### Manual diagnostic launch used during testing

This was used only to prove the service works; it is not the desired permanent startup model:

```powershell
$env:AIS_DOCUMENT_WORKFLOW_DB="C:\AradhanaSystems\platform\plugins\document-print-workflow\service\document_workflow.db"
$env:AIS_DOCUMENT_WORKFLOW_PORT="8310"
& "C:\Users\Lenovo\AppData\Local\Programs\Python\Python313\python.exe" "C:\AradhanaSystems\platform\plugins\document-print-workflow\service\app.py"
```

### Bridge credential

The QR bridge token must be stored per signed-in biller user in the approved durable credential mechanism:

- preferred: DPAPI encrypted file under the biller’s local application-data security location;
- compatibility fallback: Windows Credential Manager target `AIS.DocumentBridgeToken`;
- never: `config.txt`, source code, scripts, command history, screenshots, or this handover.

The DPAPI setter was corrected after an earlier runtime type-resolution failure. The latest successful result was:

```text
Saved encrypted Router bridge credential for this Windows user.
```

---

## 8. Biller-facing document experience

### Independent document alert

When the QR Scanner submits a billing bundle, PC2’s document alert notifier should show a non-blocking top-right toast. Verified observed form:

```text
NEW DOCUMENT READY
Pending ID documents
<bundle identifier> · Held until you choose Print documents
[Print documents now] [Dismiss]
```

Required next UX enhancement: show the customer/OCR display name in this toast. Source support for names exists in the biller popup; verify independently in the persistent alert notifier.

### Alt+P biller panel

When the biller presses `Alt+P` in Ornate:

- if recent eligible (<30 minutes) bundles exist, show a non-blocking top-right decision panel;
- show newest three eligible bundles maximum;
- include customer/OCR display name, document type, count, and bundle ID;
- if no current eligible bundle exists, show no document panel;
- never prevent the normal Ornate bill print flow.

Final intended buttons:

| Action | Effect |
|---|---|
| **Attach document** | Cache the selected bundle; it is composited only into the next eligible P355 customer copy. Bill first copy is unchanged. |
| **Print documents** | Sends only the selected documents to P355. It does not touch bill printing. |
| **Dismiss** | Makes no document/bill print change. |

Old / removed intent:

- No **Print bill normally** button. A popup must not issue a bill print command.
- No **Wait 60 seconds** flow in final UX.
- No mandatory modal blocking the biller.

### Known code status

The non-blocking decision experience was tested at various points, but code on PC2 may lag the final source package because multiple staged copies were manually copied during testing. Before final deployment, deploy one coherent release only; do not cherry-pick individual `.py` files in production.

---

## 9. P355 document composition rules

### Source

```text
C:\AradhanaSystems\platform\plugins\document-print-workflow\renderer\p355_document_renderer.py
```

### Required final geometry

#### Terms and conditions

- Terms occupy the upper 50% of the reverse page.
- Terms are rendered horizontally; portrait source terms rotate as needed.

#### Documents

- Documents occupy only the lower 50% of the reverse page.
- The normal bill remains full page on the front side according to existing P355 letterhead workflow.

#### ID-card mode

- QR `id_card` mode.
- Maximum individual card slot: **6 cm wide × 4 cm tall**.
- One card uses a card-sized lower-half slot, not an enlarged full page.
- Multiple cards are arranged as cards in the lower half.
- Target layouts support 2, 4, and up to 6 cards. If six cannot fit at maximum size, reduce evenly so all fit.

#### Full-page mode

- QR `pdf` mode / full-page source still uses only the lower 50% of the P355 reverse.
- One full-page document uses the lower half; portrait documents rotate where necessary.
- Do not change QR Scanner’s existing mode controls while enforcing this output rule.

### Verified render test

The script produced:

```text
C:\PrintBridge\document_test_output\TEST_ONLY_P355_DOCUMENT_LAYOUT.pdf
```

Latest noted result:

```text
OK: ...TEST_ONLY_P355_DOCUMENT_LAYOUT.pdf (2 pages; PDF only, nothing printed)
```

### Still required before declaring final P355 layout complete

1. Test 2 real/scanned ID cards.
2. Test 4 cards.
3. Test 6 cards (must reduce evenly if required).
4. Test one full-page PDF selected from QR Scanner full-page mode.
5. Test one attached bundle with a real P355 bill capture.
6. Confirm duplex physical paper order and no extra blank pages.

---

## 10. Existing Ornate router

### Existing configuration observed on PC2

```text
MasterEnabled=true
PcRole=PC2 (Hub)
Copy1Printer=HP LaserJet P1007
Copy2Printer=355 Letterhead Capture
ForceCopy1Printer=
ForceCopy2Printer=
SessionGapSeconds=20
DocumentWorkflowEnabled=true
DocumentWorkflowRoot=C:\AradhanaSystems\platform\plugins\document-print-workflow
DocumentWorkflowApi=http://127.0.0.1:8310
DocumentScannerApi=https://print.aradhanajewellers.com
```

### Existing physical printer inventory observed on PC2

```text
HP LaserJet P1007                              USB001
HP Laser MFP 355sdnw (05:32:A7)               WSD-...
355 Letterhead Capture                         Bullzip PDF Driver
Aradhana PDF Capture                           Microsoft PS Class Driver
Aradhana Capture Legal                         HP LaserJet P1007
```

### Existing route mechanism

1. Router sees an Ornate `Voucher Print` window.
2. Router sees an Ornate standard `Print` dialog.
3. Router selects either P1007 or the virtual `355 Letterhead Capture` printer.
4. P355 capture enters `C:\PrintBridge\incoming_355`.
5. Router/overlay worker composes letterhead / terms / attached documents.
6. Sumatra submits the composed PDF duplex to `HP Laser MFP 355sdnw (05:32:A7)`.

### Why the old routing failed

Ornate sometimes opens another `Voucher Print` window for URD or extra copies. It does not expose a reliable copy ordinal, document type, or selected Voucher Format via ordinary Win32 controls or UI Automation.

Old timing strategy:

```text
if new Voucher Print appears within 20 seconds → treat as later copy/P355
otherwise → treat as new bill/P1007
```

This was proven unsafe. A late URD can arrive after the timeout and be wrongly sent to P1007.

Log evidence from before the fix:

```text
2026-09-06 15:48:22 ROUTE: new Ornate bill session; first copy=P1007, later copies=P355.
2026-09-06 15:48:30 APPROVED ... (copy 1). Selected printer 'HP LaserJet P1007'.
2026-09-06 15:48:31 APPROVED ... (copy 2). Selected printer '355 Letterhead Capture'.
2026-09-06 15:48:32 ROUTE: new Ornate bill session; first copy=P1007, later copies=P355.
...
2026-09-06 15:48:45 APPROVED ... (copy 1). Selected printer 'HP LaserJet P1007'.
```

---

## 11. New visual-format router release

### Design

The new release does not use timeout alone. It requires both signals:

1. a real foreground Ornate `Alt+P` event arms a new bill session briefly;
2. Windows `PrintWindow` captures only the visible `Voucher Print` dialog;
3. the Voucher Format area is compared in memory with an approved office-sales visual reference;
4. only the first standard Print dialog from a matching armed session may select P1007;
5. second copy, URD, extra copies, unknown format, capture failure, missing reference, or no fresh `Alt+P` arm all route to P355.

This uses no whole-screen recorder, cloud upload, remote OCR, or retained runtime screenshot.

### Reference image

```text
office-sales-voucher-format-reference.png
SHA-256: C059CBCF923E5331FE589364783B9365BA33CC43AD3C70D6BF7E3140D00C729F
```

It was captured on PC2 using Windows `PrintWindow` from the normal office Sales Voucher dialog.

### New EXE artifact

```text
AradhanaOrnateAutoPrint.exe
SHA-256: 8898BCA405D34604C158965F9BE8E82A8A3E413A3955C6D2336971AA991372DC
```

### Staged release package

```text
\\PC2\PrintBridge\deploy\document_workflow_20260906\voucher_format_router_20260906\
  AradhanaOrnateAutoPrint.exe
  Install_Aradhana_Ornate_AutoPrint.bat
  office-sales-voucher-format-reference.png
  SECURITY_REVIEW.md
```

### Source changes in the release

- `PrintWindow` window-only capture.
- Office Sales format fingerprint comparison.
- hybrid `Alt+P` + visual-format confirmation.
- P355 default on uncertainty.
- installer copies the companion reference image alongside the EXE.

### Build verification

The router source compiled successfully with .NET Framework C# compiler. The release EXE hash is above.

### NPAV deployment incident

The installer printed `Installed and started`, but NPAV removed the EXE from:

```text
C:\ProgramData\Aradhana\OrnateAutoPrintTray\AradhanaOrnateAutoPrint.exe
```

The companion PNG remained. This occurred twice with the new EXE.

The package’s `SECURITY_REVIEW.md` documents the scope and hashes. It is not a bypass mechanism. A subsequent approved installation succeeded and its process/hash/reference were verified at 17:54 IST; controlled routing tests remain pending.

### Required verification after a permitted deployment

```powershell
Get-Process AradhanaOrnateAutoPrint | Select-Object Id,StartTime
(Get-FileHash "C:\ProgramData\Aradhana\OrnateAutoPrintTray\AradhanaOrnateAutoPrint.exe" -Algorithm SHA256).Hash
Test-Path "C:\ProgramData\Aradhana\OrnateAutoPrintTray\office-sales-voucher-format-reference.png"
```

Expected:

```text
process exists
8898BCA405D34604C158965F9BE8E82A8A3E413A3955C6D2336971AA991372DC
True
```

### Required controlled routing tests

Run only with an authorised quiet test window and real operators present.

1. **Normal GST Sales Voucher**
   - Press `Alt+P` in Ornate.
   - Use `GST Sales Voucher (A4) Shree Aradhana`.
   - Expected: first Print dialog selects P1007.
   - Expected: second bill copy selects `355 Letterhead Capture`; physical result exits through 355.
2. **URD / GST Purchase Voucher**
   - Use `GST Purchase Voucher (A4) SHREE ARADHANA JEWELLERS`.
   - Expected: never P1007; all copies P355.
3. **Extra/third copy**
   - Expected: P355.
4. **P355 capture failure / missing format reference**
   - Expected: P1007 denied; normal safe P355 route/log entry.
5. **Non-Ornate program**
   - Print from Notepad while Ornate remains open.
   - Expected: router does not auto-confirm or change the Notepad dialog.

Inspect after each test:

```powershell
Get-Content "C:\ProgramData\Aradhana\OrnateAutoPrintTray\OrnateAutoPrint.log" -Tail 80
```

Expected log language from the new release includes one of:

```text
ROUTE: confirmed Alt+P + approved office Voucher Format ... first copy=P1007, second/URD/later copies=P355.
ROUTE SAFETY: Voucher Print is not a confirmed new office session ... P1007 blocked ... P355.
ROUTE: not a confirmed new office session; later copy remains P355.
```

---

## 12. Temporary inspection tool used for format calibration

```text
C:\AradhanaSystems\projects\print-router\tools\Inspect-OrnateVoucherDialog.ps1
\\PC2\PrintBridge\deploy\document_workflow_20260906\routing_diagnostics_20260906\Inspect-OrnateVoucherDialog.ps1
```

It is diagnostic only. It:

- finds a visible Ornate-owned `Voucher Print` dialog;
- captures only that window using `PrintWindow`;
- saves its image at `C:\PrintBridge\routing_diagnostics\`;
- attempts local Tesseract only if installed;
- enumerates non-mutating Win32 and UI Automation fields.

PC2 observations:

```text
Tesseract is not installed.
```

That is not a blocker for the final visual-reference router, because the final router performs local image comparison instead of requiring Tesseract.

The tool is not required at normal runtime.

---

## 13. Payment Notifier dashboard — Documents tab

### Intended dashboard state

Bank Activity has two main tabs:

```text
Payments | Documents
```

Documents tab requirements:

- one line per customer/display name, document type, document count;
- received time and current queue status;
- individual document download links;
- **Reprint** action;
- **Resend to biller** action;
- existing KYC OCR fields remain visible for review and copy tracking.

### Implemented but not yet deployed/restarted

Changes exist in these currently modified files:

```text
payment-auditor/backend/review_api.py
payment-auditor/frontend/src/api/client.ts
payment-auditor/frontend/src/pages/BankActivityPage.tsx
```

Backend additions proxy the QR document APIs server-side and keep the bridge credential out of browser JavaScript. Intended endpoints:

```text
GET  /api/documents
GET  /api/documents/{bundle_id}/files/{filename}
POST /api/documents/{bundle_id}/reprint
POST /api/documents/{bundle_id}/resend-to-biller
```

Verification already performed locally:

```text
python compilation of review_api.py: passed
npm run build: passed
```

Before deployment:

1. Review exact git diff; the Payment Auditor working tree may contain other user changes.
2. Stage only the three named files.
3. Commit with a focused message.
4. Restart only the laptop production backend through the existing service control script during a safe dashboard window.
5. Call `GET /api/documents` from the laptop and then verify the Documents tab in browser.

### Existing dashboard production control

Known service control source:

```text
C:\AradhanaSystems\projects\payment-auditor\scripts\aradhana_service_control.ps1
```

Previously verified production client URL:

```text
http://192.168.0.12:5173
```

Existing backend: port 8000. Existing frontend: port 5173.

---

## 14. QR bridge and document sync

### `qr_bundle_sync.py`

Latest intended behavior:

1. fetch pending QR billing bundles using bridge authentication;
2. filter to bundles younger than 30 minutes;
3. take the newest three;
4. post them to the PC2 local workflow API;
5. print a compact result such as:

```json
{"synced": 2, "eligible": 2}
```

The router suppresses the Alt+P document panel when `eligible` is zero.

### Important deployment note

Latest `qr_bundle_sync.py` and local `service/app.py` changes were staged in a final workflow package but may not have been copied/restarted coherently on PC2. Do not mix files manually. Include them in a tested plugin release after router security remediation.

---

## 15. Known packages and historical staging locations

These paths were used during testing. They are not all final releases; do not blindly rerun them.

```text
\\PC2\PrintBridge\deploy\document_workflow_20260906\
\\PC2\PrintBridge\deploy\document_workflow_20260906\final_workflow_lock_20260906\
\\PC2\PrintBridge\deploy\document_workflow_20260906\copy_routing_urd_fix_20260906\
\\PC2\PrintBridge\deploy\document_workflow_20260906\routing_diagnostics_20260906\
\\PC2\PrintBridge\deploy\document_workflow_20260906\voucher_format_router_20260906\
```

Historical router hashes:

| Hash | Meaning | Do not use as final |
|---|---|---|
| `29630FF5ED33DE3464AC6485E67D0525EB245C4B56D7B0F4E2974CE6535FB1F4` | timing/state router build | no; false P1007 risk |
| `BA00D655FBDA1F9A73E99EF97009BFE765F5B92EC7903B2B43EE1FEF5E7FFDB2` | 20-second URD continuation build | no; delayed URD still unsafe |
| `8898BCA405D34604C158965F9BE8E82A8A3E413A3955C6D2336971AA991372DC` | hybrid visual-format release | source compiled; PC2 deployment blocked by NPAV |

---

## 16. OTA update work

### Location

```text
C:\AradhanaSystems\platform\ota-control
```

### Work completed

- LAN OTA server prototype.
- signed release envelope concept using RSA SHA-256.
- client verifies release manifest and ZIP hash before staging.
- smoke package `ota-smoke-test 0.0.1` staged successfully on laptop.
- loopback health was tested on port 8091.

### Not production complete

The OTA server must still receive:

1. durable service/startup configuration;
2. LAN firewall rule scoped to intended network;
3. stable certificate/private-key storage with backup and access control;
4. release-channel policy (`dev`, `beta`, `stable`);
5. per-target install scripts that validate signatures and preserve rollback;
6. production signing/release procedure approved by endpoint security.

Do not use OTA to push a router while PC2 security treatment of the binary is unresolved.

---

## 17. Git state and hygiene

### Print router repository

Repository:

```text
C:\AradhanaSystems\projects\print-router
```

Baseline latest commit observed:

```text
1c24a54 Import Ornate smart print routing system (source, overlay pipeline, binaries)
```

Current repository contains uncommitted work that predates and overlaps this session, including document-workflow wiring. Current visible modifications/untracked items include:

```text
M build-and-install/Build_Aradhana_Ornate_AutoPrint.bat
M build-and-install/Install_Aradhana_Ornate_AutoPrint.bat
M src/AradhanaOrnateAutoPrint.cs
?? assets/
?? build-and-install/AradhanaOrnateAutoPrint.document-workflow-test.exe
?? build-and-install/AradhanaOrnateAutoPrint.exe
?? build-and-install/AradhanaOrnateAutoPrint.window-watcher-test.exe
?? build-and-install/Set_AIS_Document_Bridge_Token.ps1
?? tools/
```

Do not commit every file above blindly. First separate:

1. router visual-format source and required asset;
2. document workflow changes;
3. existing historical/unrelated generated binaries;
4. secret-setter scripts (review separately; never commit a secret).

### Recommended commits

1. `router: gate P1007 by Alt+P and approved voucher-format capture`
2. `workflow: expire held QR bundles and suppress empty biller panels`
3. `dashboard: add secure QR document archive tab`
4. `ota: add signed LAN release control plane`

One logical deployable change per commit.

---

## 18. E2E test matrix — final acceptance

| ID | Scenario | Expected result | Current status |
|---|---|---|---|
| R1 | Normal Sales Voucher, first copy | P1007 only | passed 2026-09-06 after hybrid router install |
| R2 | Normal Sales Voucher, second copy | P355 | passed 2026-09-06 after hybrid router install |
| R3 | URD Purchase Voucher | P355 only | passed 2026-09-06; visual difference 21.69, P1007 denied |
| R4 | late URD/third copy | P355 only | router installed; controlled test pending |
| R5 | non-Ornate Notepad print | no auto action | router installed; controlled test pending |
| D1 | QR Send for Billing | visible held queue/document toast, no automatic print | partially tested |
| D2 | no recent queued document + Alt+P | no document panel | source staged; PC2 coherent deployment pending |
| D3 | eligible QR document + Alt+P | non-blocking panel with customer/OCR name | partial; customer name still needs explicit verified UI test |
| D4 | Attach document | only P355 customer copy gets lower-half document layout | renderer tested separately; full live merge pending |
| D5 | Print documents | documents to P355 only; bill unchanged | partial / requires live test |
| D6 | Dismiss | no print command issued | partial / requires live test |
| D7 | queue expires after 30 min | no longer offered to biller; retained archive state | cloud implementation pushed; needs live verification |
| L1 | 1 ID card | lower-half card max 6×4 cm | visually accepted |
| L2 | 2/4/6 ID cards | evenly tiled lower-half cards | not fully tested |
| L3 | full-page doc | lower-half rotated/fitted doc plus upper terms | not fully tested |
| O1 | PC2 reboot | router + workflow API + document alerts recover automatically | not accepted |
| O2 | OTA stable update | signature/hash verified, rollback available | prototype only |

---

## 19. Recommended continuation order

1. **Run R1–R5 controlled router tests.** PC2 router process, EXE hash, and reference file are verified; now prove P1007/P355 behavior.
3. **Deploy one coherent document-workflow plugin release to PC2.** Include service, sync bridge, alert notifier, biller popup, cache, standalone queue, renderer, and startup/persistence configuration. Do not manually copy a subset.
4. **Run D1–D7 and L1–L3.** Use test documents first, then one authorised live bill only after test proof.
5. **Review/commit Payment Notifier Documents tab.** Restart laptop backend in a safe window; validate secure proxy and document actions.
6. **Make persistence real.** Verify router user startup, local workflow API task/service, alert notifier user startup, and post-reboot health on each biller PC.
7. **Finish OTA stable channel.** Then deploy future tested plugin releases centrally instead of repeated manual PC2 commands.

---

## 20. Operational commands (safe diagnostics only)

### Router status

```powershell
Get-Process AradhanaOrnateAutoPrint -ErrorAction SilentlyContinue | Select-Object Id,StartTime
Test-Path "C:\ProgramData\Aradhana\OrnateAutoPrintTray\AradhanaOrnateAutoPrint.exe"
Get-Content "C:\ProgramData\Aradhana\OrnateAutoPrintTray\OrnateAutoPrint.log" -Tail 80
```

### Workflow health

```powershell
Invoke-WebRequest "http://127.0.0.1:8310/health" -UseBasicParsing
```

Expected HTTP 200 JSON includes `status: healthy`.

### PC2 printer inventory

```powershell
Get-Printer | Select-Object Name,DriverName,PortName,Shared,Published | Format-Table -AutoSize
```

### Payment Notifier dashboard

```text
http://192.168.0.12:5173/bank-activity
```

### QR Scanner

```text
https://print.aradhanajewellers.com/print
```

---

## 21. No-go conditions

Do not declare production-ready if any is true:

- PC2 router EXE absent or process absent;
- router log cannot prove P1007 only receives confirmed first Sales copy;
- `AISDocumentWorkflowApi` is manual-only or cannot survive restart;
- bridge token is in plaintext config/script/history;
- document popup blocks or prints the bill itself;
- document print can reach P1007;
- queue expiry not demonstrated;
- 2/4/6 card render variants not tested;
- dashboard documents route can expose bridge token to browser;
- OTA updater applies an update without manifest/hash/signature verification and rollback.

---

## 22. Final concise status

The architecture is sound and the main components exist. The project is **not yet production-complete** because PC2 endpoint security removed the new router EXE, workflow persistence has not passed reboot acceptance, and the final real-world document attachment matrix remains incomplete.

The immediate priority is a verified secure PC2 router restoration, then controlled routing tests, then one cohesive document workflow release.

---

## 23. AIS foundation update — 2026-09-07

Implemented on the development/control-plane laptop. No production PC was changed in this update.

### Added

| Component | Location | Purpose |
|---|---|---|
| AIS registry | `C:\AradhanaSystems\platform\core\ais.registry.json` | One declared inventory of projects, plugins, services, owners, ports and OTA targets. |
| Device registry | `C:\AradhanaSystems\platform\core\ais.devices.json` | Approved laptop, PC2 and Dell roles/addresses. No secret data. |
| Plugin manifest contract | `C:\AradhanaSystems\platform\core\plugin.manifest.schema.json` | Required metadata for every new AIS plugin. |
| Workflow plugin manifest | `...\document-print-workflow\ais.plugin.json` | Declares version, contracts, runtime split and OTA target. |
| AIS Control Center | `C:\AradhanaSystems\platform\control-center\` | Mobile-friendly, loopback-only, read-only registry/health surface on port 8120 when installed. |
| OTA bundle builder | `...\ota-control\New-AISReleaseBundle.ps1` | Allow-list release payload builder with per-file hashes. |
| Workflow service installer hardening | `...\document-print-workflow\scripts\install_document_workflow_service.ps1` | Validates Python + Flask and proves local health before reporting success. |
| Workflow alert persistence | `...\install_document_alerts_startup.ps1` | User-session logon task for top-right alerts; deliberately not SYSTEM. |
| DPAPI token setup | `...\Set-AISDocumentBridgeToken.ps1` | Current-user encrypted token storage compatible with the Router. |

### Validation complete

* AIS registry validator: **valid** — 7 projects, 1 plugin, 3 devices.
* Document workflow and Control Center isolated tests: **10 passed**.
* New PowerShell scripts: parse check passed.
* No secret was added to source, registry, OTA metadata, dashboard API, or logs.
* Existing dirty worktrees were left untouched.

### Still requires physical acceptance, not code completion

* R4/R5 and D1–D7/L2–L3/O1/O2 in the matrix above.
* Production deployment of one coherent, signed workflow package to PC2.
* Payment Notifier Documents-tab restart/window and browser verification.
* OTA beta → stable promotion with documented rollback proof.

The next work unit is to assemble the coherent **document-workflow-pc2 beta** package from the new manifest and allow-list builder, then run the matrix only after package review.

### Package assembled — 2026-09-07

* Target: `document-workflow-pc2`
* Version: `1.0.0-beta.1`
* Bundle: `C:\AradhanaSystems\releases\document-workflow-pc2-1.0.0-beta.1\document-workflow-pc2-1.0.0-beta.1.zip`
* SHA-256: `F7C6612B201923E56D09D5411238E8C6AD54FFF4B96515FC001FE90A8264833E`
* Payload: 18 explicit files. Every payload hash was verified after ZIP extraction.
* State: built locally only. Not signed/published to OTA, not copied to PC2, not applied.

The release apply script preserves the current-user DPAPI bridge credential and
backs up replaced plugin files before installation. It refuses a non-elevated
session, validates the Python/Flask runtime, and requires the API health check
to pass before reporting success.

### Final static gate — 2026-09-07

* Payment Notifier backend (`review_api.py` and local KYC/OCR modules): Python compile passed.
* Payment Notifier frontend: TypeScript/Vite production build passed.
* AIS Document Workflow + Control Center tests: **10 passed**.
* AIS registry validator: **valid**.
* No production process restart, PC2 copy, printer action, OTA publish or OTA apply occurred in this gate.
