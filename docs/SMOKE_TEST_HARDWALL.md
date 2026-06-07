# Production Smoke Test Hardwall

`scripts/smoke_test_production.ps1` verifies the known-good production baseline before future merges.

## Checks

- Backend `/health` returns `healthy`.
- Backend port `8000` is listening.
- Frontend port `5173` is listening.
- Reconciliation endpoint does not return `500`.
- Ingestion status confirms the local-inbox watcher baseline when an auth token is supplied.
- Backend production logs do not contain `BankAlert.bill_id` or `SMSAlert.bill_id` tracebacks.
- Production startup uses an explicit Python executable, not the `py` launcher.

## Authentication

The script does not hardcode credentials. For authenticated endpoint field validation, provide an existing session token:

```powershell
$env:SMOKE_TEST_SESSION_TOKEN = "<active-session-token>"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\smoke_test_production.ps1
```

If no token is supplied and an endpoint returns `401`, the script marks the route as reachable and auth-protected.

## Expected Ingestion Baseline

When authenticated, ingestion status must show:

- `watcher_path = C:\AradhanaAuditor\invoice_inbox`
- `local_inbox_path` exists
- `sync_running = true` or `last_sync_error` contains a retry reason
- `local_pdf_count > 0`

## Failure Handling

The script prints `PASS` or `FAIL` for each check and exits non-zero if any check fails.

Rollback command for this hardwall commit:

```powershell
git revert <commit-hash>
```
