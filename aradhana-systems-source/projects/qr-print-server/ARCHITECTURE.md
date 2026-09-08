# Aradhana QR Print Server - System Architecture (v3)

This document outlines the technical architecture, workflows, and deployment standards for the Aradhana QR Print Server.

## 1. High-Level Architecture

The system uses a decoupled architecture to bridge public web uploads with local physical printing.

*   **Cloud Server (Central Hub):** A public-facing Flask application that receives files from users and manages the print queue.
*   **Local Print Agent (Edge Worker):** A background service running on the local shop PC that polls the Cloud Server, processes documents, and communicates with the physical printer.

---

## 2. Cloud Server Architecture

*   **Framework:** Flask (Python)
*   **Database:** SQLAlchemy (SQLite) for job tracking and persistence.
*   **Storage:** Local filesystem directory (`/uploads`) for temporary storage of uploaded assets.
*   **Core Responsibilities:**
    *   Hosting the user-facing upload interface.
    *   Validating file types (`.jpg`, `.jpeg`, `.png`, `.pdf`) and batch sizes (max 12 files).
    *   Generating unique, human-readable Queue IDs (`AR-YYYYMMDD-XXX`).
    *   Providing a REST API for the Local Print Agent.
    *   Providing an Admin Dashboard for queue monitoring and maintenance.

---

## 3. Local Print Agent Architecture

*   **Framework:** Python (Background Loop)
*   **Polling Mechanism:** Requests pending jobs every 5-10 seconds via HTTP.
*   **Layout Engine:**
    *   **Pillow (PIL):** Used for image rotation, resizing, and normalization.
    *   **ReportLab:** Used to generate print-ready A4 PDF layouts.
*   **Print Driver:** **SumatraPDF** (CLI Mode). Used for silent, non-interactive printing to specific Windows printer drivers.
*   **Core Responsibilities:**
    *   Securely downloading assets from the Cloud Server.
    *   Generating PDF layouts based on the `print_mode` (Standard PDF or ID Card Grid).
    *   Managing local job state and ensuring idempotency (no double-prints).
    *   Reporting detailed status/error logs back to the Cloud Server.

---

## 4. API Endpoints (Agent Communication)

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/agent/jobs/pending` | `GET` | Returns a list of jobs with `status="pending"`. |
| `/api/agent/jobs/<job_id>/status` | `PATCH` | Updates job status (`printing`, `completed`, `failed`) and attaches error messages. |
| `/media/<job_id>/<filename>` | `GET` | Downloads the raw file for processing. |

---

## 5. Print Workflow & Queue Lifecycle

### Flow:
1.  **Submission:** User uploads 1-12 files via mobile browser.
2.  **Creation:** Cloud Server creates a record with `status="pending"`.
3.  **Discovery:** Agent polls the server and fetches the job metadata.
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

## 6. Deployment Workflow

1.  **Server Setup:** Deploy `cloud-server/` to a reachable host (e.g., Heroku, VPS, or local network).
2.  **Environment Config:** Configure `.env` on both server and agent (Printer Name, API URL, Secrets).
3.  **Local Dependencies:** Install Python 3.11+ and SumatraPDF on the shop PC.
4.  **Agent Installation:** Use `install_service.bat` (NSSM) or `install_autostart.bat` (Task Scheduler).

---

## 7. Startup Automation

The project supports two methods for ensuring the Agent runs 24/7 on Windows:

*   **NSSM (Recommended):** Installs the agent as a true Windows Service. Managed via `local-print-agent/install_service.bat`.
*   **Task Scheduler:** Runs the agent at system startup under the `SYSTEM` account. Managed via `local-print-agent/install_autostart.bat`.

---

## 8. Recovery Procedures

*   **Printer Jams:** The agent will timeout after 60s. Clear the printer queue manually and restart the Agent service.
*   **Stuck Queue:** Use the Cloud Server `/admin` dashboard to "Clear Pending Queue" if jobs are backed up.
*   **Network Failure:** The Agent uses exponential retry/polling logic; it will automatically resume printing once the connection is restored.
*   **Logs:**
    *   Agent logs: `local-print-agent/logs/agent.log`
    *   Service logs: `local-print-agent/logs/nssm_stderr.log`

---

## 9. Known Dependencies

*   **Python Libraries:** `flask`, `flask-sqlalchemy`, `requests`, `pillow`, `reportlab`, `python-dotenv`.
*   **External Binaries:**
    *   **SumatraPDF:** Required for PDF rendering/printing.
    *   **NSSM (Optional):** Required for service installation.

---

## 10. Production Deployment Checklist

- [ ] `PRINTER_NAME` matches exactly as shown in Windows "Printers & Scanners".
- [ ] `SUMATRA_PATH` points to a valid `SumatraPDF.exe`.
- [ ] `CLOUD_SERVER_URL` is accessible from the shop PC.
- [ ] `ADMIN_SECRET` is set on the server to protect the queue.
- [ ] Printer is set as "Online" and has paper/toner.
- [ ] Agent service is confirmed "Running" via `services.msc` or Task Scheduler.
