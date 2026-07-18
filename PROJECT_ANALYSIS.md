# AMBIC Payment Auditor — Current Architecture

This document replaces the original generated inventory, which referenced deleted files and the pre-SaaS single-tenant design.

## Runtime entry points

- `backend/review_api.py` — production FastAPI application and API/static-frontend host.
- `frontend/src` — Vite/React/TypeScript single-page application.
- `backend/database.py` — per-tenant SQLAlchemy engine/session resolution.
- `backend/business_registry.py` — business profiles and global session-token-to-tenant index.
- `backend/tenant_context.py` — request-to-tenant resolution.

`backend/main.py` and `backend/auth.py` were deleted because they were an unused in-memory demonstration application. Do not recreate or launch them.

## Data model

Each registered business currently receives `businesses/<slug>/data.db`. Core models include users, OTPs, sessions, bills, payments, bank alerts, SMS alerts, cheques, maintenance sessions, and audit logs. Tenant isolation comes from selecting the business database before a route obtains a session, not from a `tenant_id` column.

## Ingestion

- `backend/pdf_ingestion.py` — tenant-scoped invoice share watcher and periodic scan.
- `backend/email_poller.py` — per-tenant IMAP bank-alert polling.
- `backend/sms_poller.py` — per-tenant authorised SMS inbox polling.
- `backend/reconciliation/` — matching, status, evidence, holiday, and SLA logic.
- `backend/prime_adapter.py` / `backend/ornate_adapter.py` — ERP normalisation adapters.

The Windows Prime scripts remain business-specific edge utilities and still contain legacy paths. They are not safe to execute as shared hosted workers until they accept an explicit tenant configuration.

## Authentication and RBAC

The live path is `backend/auth_service.py`: employee ID, password, email OTP, and database-backed sessions. `backend/rbac.py` defines roles, while individual API routes also enforce role lists. These two permission descriptions must be reconciled before launch because the inherited tests currently disagree with the mapping.

## Known incomplete paths

- The React frontend does not yet send or derive a business slug.
- `/reviews/open`, `/escalations/open`, and `/reports/owner` still contain deterministic mock/in-memory data.
- The audit-log page is an empty shell and does not fetch stored audit records.
- Some reconciliation/Prime helpers still use legacy `C:\Aradhana` paths or the default-tenant compatibility shim.
- SQLite files and flat JSON session indexing require a single persistent instance; they are not horizontally scalable SaaS storage.

See `LAUNCH_READINESS_AUDIT.md` for severity, evidence, and release gates.

