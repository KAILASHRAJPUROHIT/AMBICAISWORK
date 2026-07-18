# AMBIC SmartQR — System Architecture

## Overview

SmartQR separates a public Flask upload/queue service from a Windows print agent installed beside each tenant's printer.

```text
Customer phone -> HTTPS upload -> tenant-scoped queue
                                      |
                                      v
                         outbound polling with X-Agent-Key
                                      |
                                      v
                         Windows agent -> SumatraPDF -> printer
```

## Tenant model

- Profiles: `cloud-server/tenants/<slug>/profile.json`.
- Job rows: shared SQLAlchemy database with indexed `tenant_slug`.
- Tenant discovery: `?tenant=` or `tenant_slug` cookie for browser flows.
- Agent authentication: rotatable profile `agent_api_key` sent as `X-Agent-Key`.
- Admin/staff data: queries are scoped by the resolved tenant.
- Media downloads: tenant-scoped job lookup plus an unguessable per-job access token.
- Document encryption: uploaded files are encrypted at rest with a per-tenant `encryption_key`
  (profile secret, alongside `admin_secret`/`agent_api_key`), decrypted only in-memory when
  serving an authenticated request — plaintext is never written back to disk.
- Document retention: `document_retention_sweep()` deletes a completed/failed job's files
  `DOCUMENT_RETENTION_HOURS` (default 2h) after its last update, and stale pending/printing jobs
  after `STALE_JOB_RETENTION_HOURS` (default 24h); the job row itself is kept for history.

The JSON profile and SQLite defaults require a single persistent instance. A horizontally scaled or ephemeral deployment needs managed tenant storage, database migrations, object storage, and shared session/secret handling.

## Queue lifecycle

1. Customer uploads 1–12 supported files.
2. Server creates a tenant-scoped `pending` job and per-job media token.
3. That tenant's agent polls `/api/agent/jobs/pending` with `X-Agent-Key`.
4. Agent patches the job to `printing`.
5. Agent downloads media, builds any required layout, and invokes SumatraPDF.
6. Agent patches the job to `completed` or `failed`.

States are `pending`, `printing`, `completed`, and `failed`. The edge agent also persists `printing`, `printed`, and `completed` in `agent_state.db`; ambiguous retries are held for manual review. The server still needs an operator-facing stuck-job lease/recovery workflow.

## Core endpoints

| Endpoint | Method | Control |
|---|---:|---|
| `/api/agent/jobs/pending` | GET | `X-Agent-Key`; returns only that tenant's jobs |
| `/api/agent/jobs/<job_id>/status` | PATCH | `X-Agent-Key`; tenant-scoped update |
| `/media/<job_id>/<filename>` | GET | resolved tenant plus per-job access token |
| `/setup` | GET/POST flow | creates tenant profile/secrets |
| `/admin` | browser flow | tenant-scoped staff/admin session |

## Deployment boundaries

- Cloud service: HTTPS, managed database/object storage, rate limiting, central logs, backups.
- Edge agent: Windows 10/11, Python 3.11/3.12, SumatraPDF, outbound HTTPS only.
- Printer credentials/driver remain on the tenant's PC; they do not belong in the cloud profile.

## Release checklist

- [ ] Two-tenant isolation test passes.
- [ ] Upload/media token tests pass.
- [ ] Agent dependency audit is clean.
- [ ] Correct printer, tenant slug, and agent key verified.
- [ ] Crash during download, print, and completion callback tested without duplicate output.
- [ ] Persistent database/object storage and backup restore verified.
- [ ] Rate limits, staff auth, secret rotation, monitoring, and retention policy enabled.

See `SAAS_HANDOVER.md` and `LAUNCH_READINESS_AUDIT.md` for current status.
