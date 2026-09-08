# AIS Cloud Foundation

Cloud-ready control-plane foundation for Aradhana Jewellers.

It is intentionally separate from the current Windows-only AIS dashboard and local control-plane. That preserves live local operations while cloud routes are introduced safely.

## Routes

The gateway owns the future public path contract:

- `/` — AIS owner overview
- `/payments` — payment notifier module
- `/documents` — document workflow module
- `/print` — QR print module
- `/catalogue` — catalogue and capture module
- `/gold` — gold rate module
- `/api/v1/*` — authenticated plugin/agent API

## Local run

```powershell
cd C:\AradhanaSystems\platform\ais-cloud
C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe -m pip install -r gateway\requirements.txt
$env:AIS_ENVIRONMENT = 'development'
C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn gateway.app.main:app --host 127.0.0.1 --port 8180
```

Open `http://127.0.0.1:8180/health`.

## Production contract

Use Azure Container Apps, Azure Database for PostgreSQL, Blob Storage and Key Vault. Set these values through Key Vault/Container Apps secrets, never in source:

- `AIS_ENVIRONMENT=production`
- `AIS_DATABASE_URL=postgresql://...`
- `AIS_AGENT_TOKEN=<random 32+ byte value>`
- `AIS_OWNER_TOKEN=<random 32+ byte value>`

In production, all API access requires an owner or agent bearer token. The public web routes are read-only placeholders until the identity provider is connected.

## Safety boundary

This gateway records health and work metadata. It never sends a print job, runs a command on an agent, stores KYC files, or exposes LAN service ports publicly. Hardware actions remain in signed local AIS agents that make outbound HTTPS calls.
