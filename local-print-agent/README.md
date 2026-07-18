# AMBIC SmartQR — Local Print Agent

Windows edge worker that polls the SmartQR cloud queue, downloads a tenant's files, creates A4/ID-card PDF layouts, invokes SumatraPDF, and reports job status.

## Actual behaviour

- Authenticates polling and status calls with `X-Agent-Key`.
- Marks a job `printing` before downloading/printing and `completed` afterwards.
- Supports full-page image/PDF printing and ID-card grid layout.
- Handles multiple copies by invoking the print command once per copy.
- Records execution state in local SQLite `agent_state.db` and holds ambiguous retries for manual review.
- Writes operational logs to `logs/agent.log`.

The current implementation does **not** automatically enable duplex printing or use native Sumatra `-print-settings` copy arguments. Do not rely on those behaviours.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python agent.py
```

Required `.env` values:

```env
CLOUD_SERVER_URL=https://your-smartqr-host.example.com
PRINTER_NAME=Exact Windows Printer Name
SUMATRA_PATH=C:\Program Files\SumatraPDF\SumatraPDF.exe
TENANT_SLUG=your-business-slug
AGENT_API_KEY=rotatable-key-from-tenant-setup
```

Use `install_service.bat` with NSSM or `install_autostart.bat` with Task Scheduler only after a manual end-to-end print test succeeds.

## Recovery

If the process stops after marking a job `printing`, the ledger intentionally blocks an automatic retry. Inspect the server queue, `agent_state.db`, and agent log before an authorised operator decides whether to clear/requeue it. Never blindly resubmit a financial, identity, or customer document.
