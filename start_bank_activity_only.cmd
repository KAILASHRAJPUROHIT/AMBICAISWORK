@echo off
REM Aradhana Payment Auditor - RETIRED MODE
REM Serves ONLY the bank-activity dashboard: http://192.168.0.12:5173/bank-activity
REM
REM Invoice pipeline OFF: nothing writes to C:\Aradhana\DUPLICATE or ARCHIVE.
REM Bank alert pollers ON: the dashboard keeps receiving live bank activity.
REM To freeze the dashboard to existing data too, set both POLL vars to 0.

cd /d "%~dp0"

set AUDITOR_ENABLE_INGESTION=0
set AUDITOR_ENABLE_LIFECYCLE=0
set AUDITOR_ENABLE_EMAIL_POLL=1
set AUDITOR_ENABLE_SMS_POLL=1

set PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe

echo Starting auditor backend in RETIRED MODE (invoice pipeline disabled)...
"%PY%" -m uvicorn backend.review_api:app --host 0.0.0.0 --port 8000
