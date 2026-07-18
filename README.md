# AMBIC Payment Auditor

A multi-tenant payment reconciliation and financial-control application built with FastAPI, SQLAlchemy, and a Vite/React frontend.

Invoices are compared with bank-email and SMS evidence. Exact, policy-approved matches can clear; ambiguous, partial, delayed, reversed, duplicate, cheque, or otherwise risky cases require authorised human review.

## Current maturity

This repository is suitable for local evaluation and a controlled pilot. It is **not ready for a public multi-tenant SaaS launch**. Tenant-aware authentication and real database-backed review/report endpoints are implemented, but production storage, rate limiting, observability, billing, and disaster-recovery controls are not. See `LAUNCH_READINESS_AUDIT.md`.

The original Aradhana production tool is a separate repository. Files under `docs/legacy-prime-*` and documents explicitly marked as legacy describe that business-specific Windows/Prime integration; they are not hosted-SaaS instructions.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m backend.review_api
```

Visit `http://localhost:8000/setup` to create a disposable business and owner account. Build the frontend first when `frontend/dist` is absent:

```powershell
Set-Location frontend
npm install
npm run build
Set-Location ..
```

Prime desktop automation is optional, Windows-only, and uses a separate dependency file:

```powershell
python -m pip install -r requirements-prime-integration.txt
```

## Controlled container pilot

`Dockerfile` and `docker-compose.yml` build the React frontend and FastAPI service into one
health-checked, single-worker container. Persistent tenant data is bind-mounted from
`./businesses`; the service is exposed only on loopback so a separately configured TLS reverse
proxy can terminate public traffic.

```powershell
docker compose build
docker compose up -d
docker compose ps
```

This is a reproducible **single-host pilot topology**, not the public-SaaS architecture. Do not
increase the worker count or run multiple replicas while SQLite files and the JSON session index
remain authoritative.

## Configuration model

Each business profile lives under `businesses/<slug>/profile.json` and contains its own mailbox, alert routing, invoice share, and SMS inbox settings. Each tenant currently receives a separate SQLite database at `businesses/<slug>/data.db`.

Do not commit `.env`, `businesses/`, database files, bank messages, invoice PDFs, or audit exports.

## Verification

```powershell
python -m pytest tests
Set-Location frontend
npm run lint
npm run build
```

The suite currently passes 148 tests. A release remains blocked by the deployment and operational gates documented in `LAUNCH_READINESS_AUDIT.md`.

## Documentation

- `SAAS_HANDOVER.md` — architecture and current limitations
- `LAUNCH_READINESS_AUDIT.md` — forensic release assessment and launch gates
- `DOCS_BANK_EMAILS.md` — per-tenant bank-alert configuration
- `FIREWALL_RECOMMENDATIONS.md` — hosted and local-edge network guidance
