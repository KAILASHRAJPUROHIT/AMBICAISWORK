# AIS end-to-end handover — 7 September 2026

## Purpose

This document transfers the current Aradhana Jewellers systems work to the next engineer. It is an operational record, not a deployment claim. Treat live billing, payment and printer paths as production-sensitive.

## Owner decisions already made

| Area | Decision |
| --- | --- |
| Product naming | Customer-facing software uses **Aradhana** first. Use “Powered by AMBIC DIGITAL” only in splash, About and design material. |
| System direction | AIS is the Aradhana internal control plane. All tools become compatible plugins with shared login, device/IP/user audit, OTA update capability and clean shared code. |
| Network | Normal operation must be LAN/Wi-Fi locked. Cloud exposure is limited to the AIS portal and carefully authenticated outbound agents. |
| Source location | Active source must live under `C:\AradhanaSystems`. |
| Cloud domain | Target portal: `ais.aradhanajewellers.com`. Keep existing `print.aradhanajewellers.com` working until AIS `/print` passes beta acceptance. |
| Cloud posture | Hybrid first: local services and printers stay local; cloud is portal, identity, audit, releases and synchronised data. |
| Security | Security first. No public printer control, remote shell, raw bank data or document payloads via the current cloud gateway. |

## Machine / network inventory

| Asset | Role / known address | Notes |
| --- | --- | --- |
| Home laptop | AIS development/control host; `192.168.0.12` | Current source, payment stack, AIS control stack and OTA host. |
| PC2 / Billing PC | Ornate billing, print-router integration | Production-sensitive. User `PC2\\Lenovo` was used during router work. |
| Dell server | Other local server / future agent target | Do not deploy agent until production credentials exist. |
| QR print server | Existing hosted scanner at `https://print.aradhanajewellers.com` | It queues/scans documents. Do not change its normal UI without a controlled test. |
| P1007 | First-copy printer | Expected first routing target for the applicable voucher path. |
| HP Laser MFP 355sdnw | Physical P355 target | Current 355 capture/overlay route sends to this device when available. Printer was later reported down; router work is on hold. |

## Canonical local structure

```
C:\AradhanaSystems\
  platform\
    ais-owner-console\             # current AIS dashboard frontend/source
    ais-local-control-plane\       # local AIS API/source
    ais-cloud\                     # cloud-ready gateway, agent, Azure IaC
    core\ais.registry.json          # canonical registry
    control-center\                # current AIS Control Center
    ota-control\                   # AIS OTA server
    plugins\document-print-workflow\
  projects\
    payment-auditor\               # active payment notifier/dashboard code
```

Legacy `C:\DEEPSEEK HARNESS` remains only as a rollback/reference copy. No active AIS owner-console process should run from it.

## Verified AIS local runtime

Verified on 7 September before this handover:

| Component | Source | Address | State |
| --- | --- | --- | --- |
| AIS owner console | `C:\AradhanaSystems\platform\ais-owner-console` | `http://localhost:3000` | Login, project list and events verified. |
| AIS local control plane | `C:\AradhanaSystems\platform\ais-local-control-plane` | `http://127.0.0.1:4317` | Healthy. |
| AIS project scanner | `...\ais-owner-console\scripts` | `http://127.0.0.1:8787` | Healthy. |
| AIS cloud gateway, development only | `C:\AradhanaSystems\platform\ais-cloud` | `http://127.0.0.1:8180` | Docker health verified. Loopback only. |
| Payment API | `C:\AradhanaSystems\projects\payment-auditor` | `http://127.0.0.1:8000` | Healthy. |
| Payment frontend | same project | `http://192.168.0.12:5173` | Running when last verified. |
| AIS OTA | `C:\AradhanaSystems\platform\ota-control` | `http://192.168.0.12:8091` | Healthy. |
| AIS Control Center | `C:\AradhanaSystems\platform\control-center` | `http://127.0.0.1:8120` | Installed and verified. |

Useful verification commands on home laptop:

```powershell
Invoke-WebRequest 'http://127.0.0.1:8180/health' -UseBasicParsing
Invoke-WebRequest 'http://127.0.0.1:8120/health' -UseBasicParsing
Invoke-WebRequest 'http://127.0.0.1:8000/health' -UseBasicParsing
Invoke-WebRequest 'http://192.168.0.12:8091/health' -UseBasicParsing
Get-Content 'C:\AradhanaSystems\platform\core\ais.registry.json'
```

Do not restart live payment, QR or printer services merely to inspect them.

## AIS owner console

### Current status

- Central source copied and cut over successfully.
- Cutover used `C:\AradhanaSystems\platform\scripts\Invoke-AISConsoleCutover.ps1`.
- Script scope was intentionally narrow: owner console, local control plane and scanner only.
- It did **not** restart payment notifier, QR server, document workflow, Ornate router, printers or OTA.
- Owner console was redesigned toward practical pages: Today, Tools, Work Queue and Admin; user later said it still needed less technical clutter and more business information. Continue the redesign before public use.

### Temporary login

- Owner-selected temporary master login: `admin` / `admin`.
- This is not adequate for a cloud deployment.
- Replace it before public/LAN-wide rollout with individual users, roles, password reset, session expiry, MFA for owner/admin and immutable audit records.
- Never repeat private tokens, API keys or password hashes in chat, handover or browser logs.

## AIS cloud gateway — implemented foundation

Path: `C:\AradhanaSystems\platform\ais-cloud`

### Present functions

- FastAPI gateway with `/health`.
- Plugin/service registry exposure.
- Owner session/bearer authentication primitives.
- Agent bearer authentication primitives.
- Audit event foundation.
- Outbound-only Windows health agent:
  `agents\windows\ais_health_agent.py`.
- Docker image / compose configuration.
- Agent test reported home laptop healthy, with payment API, payment web, OTA, Control Center and gateway healthy.

### Explicit safety boundary

Current gateway does **not**:

- accept remote command execution;
- operate printers;
- expose a remote shell;
- upload/download KYC documents;
- control QR scanning;
- expose bank message content;
- listen on LAN or Internet.

Docker mapping is loopback-only: `127.0.0.1:8180:8080`.

### Production work still required

1. Provision a cloud tenant and secure secret store.
2. Generate unique production secrets; do not reuse development placeholders.
3. Add individual identity/roles.
4. Give every PC a unique agent identity and revoke capability.
5. Add signed OTA release manifests, staged rollout, rollback and health gates.
6. Connect dashboard pages to versioned gateway APIs.
7. Add data retention policies, backup restore tests and security logging.

## Azure infrastructure preparation

Files created:

```
C:\AradhanaSystems\platform\ais-cloud\infra\azure\main.bicep
C:\AradhanaSystems\platform\ais-cloud\infra\azure\main.parameters.example.json
C:\AradhanaSystems\platform\ais-cloud\infra\azure\Deploy-AISAzure.ps1
C:\AradhanaSystems\platform\ais-cloud\infra\azure\README.md
```

The intended foundation includes Log Analytics, Key Vault with RBAC, private Blob storage, Container Registry, managed identity and Azure Container Apps with HTTPS/liveness/readiness. It is intentionally **not deployed**. No Azure resources were created and no Azure bill should exist from this work.

PostgreSQL was intentionally omitted from the template until VNet/subnet/private-DNS design is approved. Do not take the shortcut of placing a production database behind a broad public firewall rule.

`az` CLI was not installed on the laptop at last check. Run a `what-if` first after installing Azure CLI and signing in. Do not run `-Apply` until subscription, Central India region, resource group, budget alerts, secrets and private network are chosen.

## Cloud cost decision context

- Google AI Pro is not Google Cloud hosting or infrastructure credit.
- Google Cloud/Firebase have free tiers for a static frontend/prototype and limited serverless workload. They do not make a permanent AIS database, document store, OTA pipeline and always-on backend free.
- Azure Container Apps has monthly free grants but always-on production plus managed PostgreSQL, logs, storage and egress are billable.
- Keep laptop + LAN as active local runtime during development. Cloud should be introduced as an audited, paid production control plane when budget is approved.
- For any provider, create budgets, cost alerts and a hard monthly review before deployment.

## Payment notifier / bank activity dashboard

Active code: `C:\AradhanaSystems\projects\payment-auditor`.

### Required behaviour agreed with owner

- Shared transaction/UTR copy state across dashboard and any popup, across all PCs:
  - fresh = blue;
  - copied once = green;
  - copied two or more times = red.
- Copying from popup must update dashboard state immediately.
- Clipboard must receive only the transaction/UTR identifier, not surrounding text.
- Last three/four transaction resend was requested earlier; verify current action path before changing data.
- Bank API endpoint previously returned a 502; inspect service logs and upstream email ingestion before assuming UI fault.
- Dashboard needs Payments and Documents as top-level tabs.
- KYC Document OCR section needs rows containing customer name, type, count, download, reprint and resend-to-biller actions.

### Current risk

Bank email ingestion was shown as `ERROR` in dashboard screenshots. Treat this as unresolved until logs identify the current provider/API failure. Do not claim it is healthy solely because payment API is listening.

## Document print workflow / QR to billing integration

Plugin root:

```
C:\AradhanaSystems\platform\plugins\document-print-workflow
```

Key components:

```
service\app.py                         # Flask workflow API; PC2 local port 8310
bridge\biller_popup.py                 # Ornate Alt+P decision UI
bridge\document_alert_notifier.py      # top-right QR queue alerts
bridge\qr_bundle_sync.py               # fetches held QR bundles into workflow
bridge\cache_bundle.py                 # caches a named bundle locally
renderer\p355_document_renderer.py     # 2-page P355 layout generator
scripts\run_p355_dummy_render_test.py  # PDF-only rendering check
```

### Workflow behaviour requested/implemented direction

1. QR scanner produces a document bundle with OCR/customer metadata and a source print mode.
2. QR scanner must offer two routes:
   - **Send for billing**: hold in biller queue; no direct print.
   - **Direct to printer**: print documents only to P355; never touch bill print.
3. Queued documents trigger a persistent top-right non-blocking alert on biller PCs. It includes customer name when scanner/OCR provides it.
4. When biller presses Alt+P in Ornate, only bundles less than 30 minutes old should be considered. Show last three eligible bundles.
5. Decision popup buttons must be:
   - **Attach document**: the sole option that modifies the P355 bill-copy flow.
   - **Print documents**: documents only to P355; no bill command.
   - **Dismiss**: preserve normal Ornate bill flow; no bill print command is sent by popup.
6. If no action is taken, normal Ornate printer handling continues.
7. Any queue item not attached within 30 minutes is removed from active queue. Historical source/archive must remain available per retention policy.
8. QR source documents are retained for 365 days.

### Renderer rules — latest agreed layout

- Output is two pages, PDF-only during test.
- Terms and conditions always occupy half of page 2, horizontally oriented.
- Attached documents use the other 50% printable area.
- **Full-page source mode:** even one document must be resized into that 50% half-page area, landscape as needed.
- **ID/card source mode:** cap each card at 6 cm wide × 4 cm high.
- Multiple cards are tiled in the half-page region: target 2, 4 or maximum 6. Shrink evenly if six require it.
- QR scanner’s own functionality must not be changed merely to enforce renderer layout.
- Latest local dummy render test reported success at two pages:
  `C:\PrintBridge\document_test_output\TEST_ONLY_P355_DOCUMENT_LAYOUT.pdf`.

### Workflow API facts on PC2

- Expected endpoint: `http://127.0.0.1:8310/health`.
- It failed after reboots because task/service persistence was interrupted by NPAV and Python/Flask dependency issues.
- Manual recovery that worked:

```powershell
$env:AIS_DOCUMENT_WORKFLOW_DB='C:\AradhanaSystems\platform\plugins\document-print-workflow\service\document_workflow.db'
$env:AIS_DOCUMENT_WORKFLOW_PORT='8310'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python313\python.exe' 'C:\AradhanaSystems\platform\plugins\document-print-workflow\service\app.py'
```

This is a temporary foreground process, not a production service. It must be replaced with a signed/allowed service design after the printer path is stable. Do not run duplicate API instances.

### Tokens / credentials

- A bridge token was used during tests and was mistakenly deleted/re-added multiple times.
- Never write the token into this document, chat, scripts, environment screenshots or source control.
- Router token persistence on PC2 was changed to encrypted Windows-user credential storage by `Set_AIS_Document_Bridge_Token.ps1` after prior Credential Manager/DPAPI issues.
- The billing router must run under the same signed-in Windows user that owns the saved credential. A different user/admin session will not automatically have access.

## PC2 Ornate auto-print router

Installed executable path:

```
C:\ProgramData\Aradhana\OrnateAutoPrintTray\AradhanaOrnateAutoPrint.exe
```

Autostart is current user `HKCU\\Run`; it is **not** a Windows service and not a scheduled task.

Current known config example:

```ini
MasterEnabled=true
PcRole=PC2 (Hub)
Copy1Printer=HP LaserJet P1007
Copy2Printer=355 Letterhead Capture
SessionGapSeconds=20
DocumentWorkflowEnabled=true
DocumentWorkflowRoot=C:\AradhanaSystems\platform\plugins\document-print-workflow
DocumentWorkflowApi=http://127.0.0.1:8310
DocumentScannerApi=https://print.aradhanajewellers.com
```

### Critical routing facts

- The router must only auto-confirm Ornate print UI. Notepad/non-Ornate print must never auto-confirm.
- Latest observed normal routing logs showed copy 1 → `HP LaserJet P1007`, copy 2 → `355 Letterhead Capture`, and 355 capture overlay ultimately submitted to `HP Laser MFP 355sdnw (05:32:A7)`.
- A recurring fault existed: URD/third copy was sometimes routed to P1007. Several executable “fix” packages were installed during live work. Do not assume it is solved for every voucher format without physical proof.
- Strongest observed discriminator is the voucher-format selection: `GST Sales Voucher (A4) Shree Aradhana` was confirmed as the case whose second copy goes to 355.
- The latest router package installed from:
  `\\PC2\PrintBridge\deploy\document_workflow_20260906\voucher_format_router_20260906\Install_Aradhana_Ornate_AutoPrint.bat`
  and later user reported normal printing worked fine. The same package’s hash at one verified point was `8898BCA405D34604C158965F9BE8E82A8A3E413A3955C6D2336971AA991372DC`; re-verify if it changes.
- Do not install a new router EXE while current billing is busy. Stop router only from its owning Windows session/admin session before replacing it.

### Why format-aware routing was chosen

Basic sequential “copy 1 / copy 2” detection could reset a session and misroute later vouchers. Ornate’s print controls expose no reliable format string via simple child-window/control inspection. A window capture watcher was proposed to watch **only** the Voucher Print window, identify the fixed format area and guide printer selection. This should be lightweight because it activates only when that specific Ornate dialog appears, not continuously across the desktop.

The diagnostic script saved window captures under:

```
C:\PrintBridge\routing_diagnostics\voucher_20260906\
```

Local Tesseract was not installed on PC2, so diagnostic OCR was unavailable. Window captures were saved and UI Automation output confirmed controls such as `Print`, `Upload Doc`, `View`, `Close` and copy count `1`.

### Router test checklist after P355 is back

1. Confirm P1007 and physical P355 printer both online.
2. Confirm workflow API 8310 only if testing document attachment; it is not required for normal bill routing.
3. Check router process and its log.
4. Print one controlled standard GST Sales Voucher with no document action.
5. Record each physical copy and exact log lines.
6. Test a URD voucher separately; do not infer from GST result.
7. Test “Attach document” only with a TEST ONLY bundle. Verify P355 output is two pages and normal bill flow is otherwise unchanged.
8. Test “Print documents” and prove it prints documents only, never triggers bill printing.
9. Test Dismiss/unattended popup and prove it causes no print command itself.
10. Repeat Notepad negative test: no auto-confirmation.

## Antivirus / NPAV incident

NPAV repeatedly quarantined or blocked router/API executable/script paths. Symptoms included installed EXE missing, scheduled task exit code 1, and workflow service failing after reboot.

Owner stated PC2 and software are under their security administration and intended to keep runtime/deployment files in an already excluded location. Do not provide broad AV-disabling procedures. Instead:

1. Use a dedicated, least-privilege application folder.
2. Keep signed/versioned release packages and hash manifests.
3. Submit false positives to NPAV; request vendor allowlisting by hash/certificate if possible.
4. Do not exclude broad drives, Windows folders, user profile or network shares.
5. Verify protection remains enabled for all other locations.
6. Record every exception in AIS audit/change log.

## OCR assessment / next direction

- Existing catalogue tool used on-device OCR; user asked whether that can be faster.
- QR workflow currently receives OCR/customer metadata from the existing QR/scanner path; customer name appeared on payment dashboard OCR card but was missing in some biller alerts earlier.
- For Android devices: prefer on-device OCR for instant pre-classification and privacy; send only normalised fields + encrypted document upload when approved.
- For high-confidence archival/validation: use a local server OCR worker, not a cloud model by default. Avoid sending Aadhaar/PAN to third-party AI services without a documented data-processing decision and consent/legal review.
- Add confidence score, document type, OCR engine/version, source device and human correction audit to every bundle.

## Required dashboard/document features — not yet all verified as complete

The following are agreed requirements. Do not mark complete until source review and end-to-end test prove each:

- Payment Notifier dashboard top tabs: Payments and Documents.
- Documents tab list: customer name, document type, document count, received timestamp, queue state, download, reprint and resend-to-biller actions.
- 30-minute active queue expiry, while retaining 365-day archive.
- Last 3 eligible bundles shown on Alt+P, only if they were sent for billing within previous 30 minutes.
- New QR bundle triggers top-right alerts; alert includes customer name when available.
- QR scanner defaults to ID mode, if the current scanner supports persisted default without breaking user flow.
- QR scanner always routes its direct prints to P355.
- OTA source/update control: laptop builds/releases; PC2 and Dell receive verified, signed/hashed staged updates with rollback. This is architecture-ready, not completed production OTA for every tool.
- Unified identity, device/IP/user audit, roles and permissions.

## Recommended immediate sequence for the next engineer

1. Read this file and `C:\AradhanaSystems\platform\AIS_CURRENT_STATE.md`.
2. Inventory live processes and ports; do not restart services during business hours.
3. Open each active source folder, run tests/builds without modification and create a baseline manifest + Git state.
4. Finish dashboard redesign from owner workflow rather than exposing technical service internals.
5. Implement versioned plugin APIs, data contracts and audit events before connecting more projects.
6. Complete document list/queue backend and dashboard UI as a bounded change. Add automated tests for 30-minute expiry and state transitions.
7. Resume physical printer/router tests only when P355 is online and billing can tolerate a controlled test window.
8. Build an OTA release system using signed artifact manifest, health check, canary PC, staged PC2/Dell rollout and rollback. Never auto-update live print routing without a canary.
9. Select cloud provider and budget. Start with portal/API and audit only; keep local printer/QR/bank adapters local and outbound-connected.
10. Before public DNS, enforce authentication, TLS, secret store, data backup/restore test, central audit, rate limiting and incident recovery runbook.

## Do not do without explicit owner approval

- Move/delete active live data, QR archives or accounting print artefacts.
- Replace a router EXE during business hours.
- Restart payment ingestion, production QR scanner, Ornate router or printer spooler to “see if it works.”
- Expose `8000`, `8310`, `8180`, `8091`, printer services or local folders directly to Internet.
- Reuse test credentials or bridge tokens in cloud deployment.
- Make irreversible Azure/GCP/Render purchases or enable billing without owner confirmation and monthly budget.
- Store Aadhaar, PAN, bank messages or document files in Git, logs, dashboard localStorage or public cloud buckets.

## Recovery references

| Need | Reference |
| --- | --- |
| AIS state | `C:\AradhanaSystems\platform\AIS_CURRENT_STATE.md` |
| AIS registry | `C:\AradhanaSystems\platform\core\ais.registry.json` |
| Dashboard cutover | `C:\AradhanaSystems\platform\scripts\Invoke-AISConsoleCutover.ps1` |
| Cloud gateway | `C:\AradhanaSystems\platform\ais-cloud` |
| Azure plan | `C:\AradhanaSystems\platform\ais-cloud\infra\azure\README.md` |
| Payment app logs | `C:\AradhanaSystems\projects\payment-auditor\logs\production` |
| Router log on PC2 | `C:\ProgramData\Aradhana\OrnateAutoPrintTray\OrnateAutoPrint.log` |
| Router config on PC2 | `C:\ProgramData\Aradhana\OrnateAutoPrintTray\config.txt` |
| Document test PDF | `C:\PrintBridge\document_test_output\TEST_ONLY_P355_DOCUMENT_LAYOUT.pdf` |

## Handover acceptance criteria

The next engineer should report status against these exact statements:

1. AIS local dashboard/control/OTA/payment health has been checked without disruption.
2. Central source paths are confirmed; no active AIS console runs from legacy folders.
3. Every unverified document requirement is labelled pending, not assumed done.
4. PC2 router routing is not changed until physical P355 test window exists.
5. No private token/credential was copied into notes, Git or release package.
6. Cloud deployment remains zero-cost/not deployed until owner selects provider, budget and security setup.

