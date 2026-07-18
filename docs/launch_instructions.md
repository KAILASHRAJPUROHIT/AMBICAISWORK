# AMBIC Payment Auditor — Launch Instructions

## SaaS evaluation server

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Set-Location frontend
npm install
npm run build
Set-Location ..
python -m backend.review_api
```

Open `http://localhost:8000/setup` for a disposable first tenant. The live FastAPI entry point is `backend.review_api:app`; the old `backend.main:app` no longer exists.

## Important limitations

- The current React frontend supports only the sole-tenant fallback. Do not register a second real business.
- A process restart is required after onboarding so ingestion pollers start for the new tenant.
- Windows Prime utilities remain local edge scripts with legacy paths. They are not part of the hosted launch.
- Do not use production bank credentials or financial data until every pilot gate in `LAUNCH_READINESS_AUDIT.md` is complete.

## Original Aradhana launchers

`start_aradhana_auditor.bat` and `run_import_and_launch.bat` are retained for historical compatibility with the original Windows deployment. They are not generic SaaS launchers.

