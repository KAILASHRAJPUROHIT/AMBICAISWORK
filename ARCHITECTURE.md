# AMBIC SmartQR — System Architecture

This document outlines the technical architecture, workflows, and deployment standards for
AMBIC SmartQR, a multi-tenant commercial QR print platform.

## 1. High-Level Architecture

The system uses a decoupled architecture to bridge public web uploads with local physical
printing, shared across many independent businesses ("tenants") on one deployment.

*   **Cloud Server (Central Hub):** A public-facing Flask application that receives files from
    users, manages the print queue, and hosts a `/setup` wizard for onboarding new businesses.
*   **Local Print Agent (Edge Worker):** A background service running on each shop's own PC that
    polls the Cloud Server for **that business's own jobs only**, processes documents, and
    communicates with the physical printer.

---

## 2. Multi-Tenant Model

*   Each business ("tenant") is a JSON profile at `cloud-server/tenants/<slug>/profile.json`,
    holding its branding (name, logo, colors), optional social/contact links (Instagram,
    Facebook, Google review, WhatsApp, phone), an optional welcome voice clip, and three secrets:
    an `admin_secret` (protects that tenant's `/admin` actions), an `agent_api_key` (what that
    shop's local print agent authenticates with), and an `encryption_key` (per-tenant Fernet key
    for document encryption at rest — see section 2a).

### 2a. Document encryption & secure-documents mode

*   Every uploaded file is encrypted on disk with the tenant's `encryption_key`
    (`app.py`'s `_encrypt_bytes`/`_decrypt_bytes`) — this is always on, not configurable.
    Decryption happens only in-memory when serving an authenticated request (`/media/...`); the
    plaintext is never written back to disk.
    *   A tenant's `secure_documents` toggle (set in `/setup`) additionally deletes a job's
    encrypted files the moment its status becomes `completed`, instead of keeping them for the
    normal 30-day retention window. Recommended for ID cards and other sensitive documents.
    Print history for those jobs shows a "Deleted (secure)" placeholder instead of a thumbnail.
*   The active tenant for a request is resolved via a `?tenant=` query param or a `tenant_slug`
    cookie (`tenant_profile.resolve_active_slug`), bound once per request in a
    `@app.before_request` hook.
*   If no tenant can be resolved, customer-facing routes redirect to `/setup`.
*   Every `PrintJob` row is tagged with `tenant_slug`, and every admin/customer query is scoped by
    it — one business can never see another's jobs, uploads, check-ins, or social handles.

---

## 3. Cloud Server Architecture

*   **Framework:** Flask (Python)
*   **Database:** SQLAlchemy (SQLite) for job tracking and persistence, with `tenant_slug` as an
    indexed column.
*   **Storage:** Per-tenant filesystem directories (`tenants/<slug>/uploads`,
    `tenants/<slug>/checkins`) for uploaded assets and staff check-in photos.
*   **Core Responsibilities:**
    *   Hosting the tenant-branded upload interface.
    *   Validating file types (`.jpg`, `.jpeg`, `.png`, `.pdf`) and batch sizes (max 12 files).
    *   Generating unique, human-readable Queue IDs derived from the tenant's slug
        (`<PREFIX>-YYYYMMDD-XXX`).
    *   Providing an authenticated REST API for each tenant's Local Print Agent.
    *   Providing an Admin Dashboard (AMBIC's own internal branding) for queue monitoring and
        maintenance, scoped per tenant.
    *   Hosting the `/setup` onboarding wizard.

---

## 4. Local Print Agent Architecture

*   **Framework:** Python (Background Loop)
*   **Polling Mechanism:** Requests pending jobs every 5-10 seconds via HTTP, authenticating with
    an `X-Agent-Key` header set to the tenant's `agent_api_key`.
*   **Layout Engine:**
    *   **Pillow (PIL):** Used for image rotation, resizing, and normalization.
    *   **ReportLab:** Used to generate print-ready A4 PDF layouts.
*   **Print Driver:** **SumatraPDF** (CLI Mode). Used for silent, non-interactive printing to
    specific Windows printer drivers.
*   **Core Responsibilities:**
    *   Securely downloading assets from the Cloud Server (only ones belonging to its own
        tenant).
    *   Generating PDF layouts based on the `print_mode` (Standard PDF or ID Card Grid).
    *   Managing local job state and ensuring idempotency (no double-prints).
    *   Reporting detailed status/error logs back to the Cloud Server.

---

## 5. API Endpoints (Agent Communication)

All `/api/agent/*` endpoints require an `X-Agent-Key` header matching a tenant's `agent_api_key`
— this is what stops one shop's agent from ever seeing another shop's print jobs.

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/agent/jobs/pending` | `GET` | Returns pending jobs for the tenant identified by `X-Agent-Key`. |
| `/api/agent/jobs/<job_id>/status` | `PATCH` | Updates job status (`printing`, `completed`, `failed`) and attaches error messages, scoped to the authenticated tenant. |
| `/media/<job_id>/<filename>` | `GET` | Downloads the raw file for processing (tenant-scoped via `?tenant=`). |

---

## 6. Print Workflow & Queue Lifecycle

### Flow:
1.  **Submission:** User uploads 1-12 files via mobile browser, on a page branded for their shop.
2.  **Creation:** Cloud Server creates a record with `status="pending"` and `tenant_slug` set.
3.  **Discovery:** That tenant's agent polls the server and fetches only its own job metadata.
4.  **Acknowledgment:** Agent marks the job as `status="printing"` on the server.
5.  **Processing:** Agent downloads files, runs the Layout Engine, and generates a temporary PDF.
6.  **Physical Print:** Agent executes the SumatraPDF command.
7.  **Finalization:** Agent marks the job as `status="completed"`.

### States:
*   `pending`: Waiting for agent.
*   `printing`: In progress (files downloaded/sent to spooler).
*   `completed`: Successfully sent to printer.
*   `failed`: Error encountered (logged in `error_message`).

---

## 7. Onboarding a New Business

1.  Visit `/setup` on the cloud server (no tenant configured yet).
2.  Fill in business name, brand colors, and optionally logo, voice clip, Instagram, Facebook,
    Google review link, WhatsApp number, phone number. Unconfigured optional fields simply don't
    render on the customer-facing page — nothing is hardcoded to one business.
3.  Save — this returns an `agent_api_key` and `admin_secret` for that business.
4.  Paste those into the shop's local print agent `.env` (see `local-print-agent/.env.example`)
    alongside `TENANT_SLUG`.
5.  Start the agent (`python agent.py`, or install as a service/scheduled task).

---

## 8. Deployment Workflow

1.  **Server Setup:** Deploy `cloud-server/` to a reachable host (starts on a home PC, later a
    VM), accessible by every onboarded tenant.
2.  **Environment Config:** Configure `.env` on the server (see `cloud-server/.env.example`) and
    on each tenant's local agent (see `local-print-agent/.env.example`).
3.  **Local Dependencies:** Install Python 3.11+ and SumatraPDF on each shop's PC.
4.  **Agent Installation:** Use `install_service.bat` (NSSM) or `install_autostart.bat` (Task
    Scheduler) per shop.

---

## 9. Startup Automation

The project supports two methods for ensuring each shop's Agent runs 24/7 on Windows:

*   **NSSM (Recommended):** Installs the agent as a true Windows Service. Managed via
    `local-print-agent/install_service.bat`.
*   **Task Scheduler:** Runs the agent at system startup under the `SYSTEM` account. Managed via
    `local-print-agent/install_autostart.bat`.

---

## 10. Recovery Procedures

*   **Printer Jams:** The agent will timeout after 60s. Clear the printer queue manually and
    restart the Agent service.
*   **Stuck Queue:** Use that tenant's Cloud Server `/admin?tenant=<slug>` dashboard to "Clear
    Pending Queue" if jobs are backed up.
*   **Network Failure:** The Agent uses exponential retry/polling logic; it will automatically
    resume printing once the connection is restored.
*   **Logs:**
    *   Agent logs: `local-print-agent/logs/agent.log`
    *   Service logs: `local-print-agent/logs/nssm_stderr.log`

---

## 11. Known Dependencies

*   **Python Libraries:** `flask`, `flask-sqlalchemy`, `requests`, `pillow`, `reportlab`,
    `python-dotenv`.
*   **External Binaries:**
    *   **SumatraPDF:** Required for PDF rendering/printing.
    *   **NSSM (Optional):** Required for service installation.

---

## 12. Production Deployment Checklist

- [ ] Business onboarded via `/setup`; `agent_api_key` and `admin_secret` recorded.
- [ ] `PRINTER_NAME` matches exactly as shown in Windows "Printers & Scanners".
- [ ] `SUMATRA_PATH` points to a valid `SumatraPDF.exe`.
- [ ] `CLOUD_SERVER_URL` is accessible from the shop PC.
- [ ] `TENANT_SLUG` and `AGENT_API_KEY` set in the agent's `.env` and match the onboarded tenant.
- [ ] Printer is set as "Online" and has paper/toner.
- [ ] Agent service is confirmed "Running" via `services.msc` or Task Scheduler.
- [ ] A second, different test tenant confirmed isolated (its agent never sees the first
      tenant's jobs).
