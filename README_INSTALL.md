# AMBIC SmartQR Print Agent — Windows Installation

This guide installs the local edge agent on the Windows PC connected to a tenant's printer. The agent polls the AMBIC SmartQR cloud service with a tenant-scoped API key and prints only jobs returned for that tenant.

## Requirements

- Windows 10/11
- Python 3.11 or 3.12
- A configured printer
- SumatraPDF
- Administrator access only when installing a service or scheduled task

## Configure and test first

```powershell
Set-Location local-print-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `CLOUD_SERVER_URL`, `PRINTER_NAME`, `SUMATRA_PATH`, `TENANT_SLUG`, and `AGENT_API_KEY` in `.env`. Obtain the tenant slug and agent key from that business's `/setup` result. Then run:

```powershell
python agent.py
```

Submit a non-sensitive test file and confirm the correct printer receives one copy before configuring automatic startup.

## Automatic startup

Two installers are included in `local-print-agent`:

- `install_service.bat` — NSSM Windows Service; requires `nssm.exe` beside the script.
- `install_autostart.bat` — Task Scheduler alternative.

The Task Scheduler script currently expects the virtual environment/interpreter path configured inside the script. Verify that path before running it as Administrator. There is no packaged `install_ambic_smartqr_print_agent.bat` or installer ZIP in this repository.

## Operations

- `check_status.bat` — inspect the scheduled task/process and recent log lines.
- `restart_agent.bat` — restart after changing `.env`.
- `uninstall_autostart.bat` — remove Task Scheduler startup.
- Logs: `local-print-agent/logs/agent.log`.

## Safety notes

- Never reuse an `AGENT_API_KEY` across tenants.
- Do not expose a printer or agent listener to the internet; the agent should make outbound HTTPS requests only.
- The agent keeps `agent_state.db` as a durable local execution ledger and refuses to reprint jobs recorded as printing/printed/completed. Back up operational logs and test the manual review path before production.
- See `LAUNCH_READINESS_AUDIT.md` before a commercial rollout.
