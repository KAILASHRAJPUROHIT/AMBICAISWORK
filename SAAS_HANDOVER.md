# AMBIC SmartQR — SaaS Handover

**Repository:** `D:\AI_PROJECTS\AMBIC-SMARTQR`, branch `main`.

SmartQR is a multi-tenant Flask queue paired with a Windows print agent. The strongest implemented boundary is tenant-scoped queue access: every job carries `tenant_slug`, agent calls require that tenant's `X-Agent-Key`, and media links include per-job access tokens.

## Start locally

```powershell
Set-Location cloud-server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open `/setup`, create a disposable tenant, then configure `local-print-agent/.env` with its slug/key and run the agent manually.

## Important files

- `cloud-server/app.py` — Flask routes, queue, staff auth, cleanup, and agent API.
- `cloud-server/tenant_profile.py` — tenant profile and request resolution.
- `local-print-agent/agent.py` — polling/printing/status loop.
- `local-print-agent/layout_engine.py` — A4 and ID-card layouts.
- `ARCHITECTURE.md` — data flow and trust boundaries.
- `README_INSTALL.md` — accurate Windows setup.

## Not launch-ready

- SQLite/JSON/local media need persistent managed replacements for hosted scale.
- Agent now has a durable local execution ledger; the server still lacks an operator-facing stuck-job lease/recovery workflow.
- Task Scheduler scripts now use the repository-local `.venv`; a packaged and signed installer is still missing.
- No billing/subscription lifecycle, central observability, incident process, or verified disaster recovery.
- Commercial printer/driver variants and service-account permissions need a supported installation matrix.

Read `LAUNCH_READINESS_AUDIT.md` before deployment.
