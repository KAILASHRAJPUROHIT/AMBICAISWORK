# AMBIC Payment Auditor — Forensic SaaS Launch Audit

**Assessment:** NO-GO for public multi-tenant SaaS. Suitable only for local evaluation or a tightly controlled single-business pilot after the pilot gates below are completed.

## Critical release blockers

1. **Production storage:** tenant SQLite files, JSON profiles, and the JSON session index require one persistent host and cannot safely support horizontal scaling, ephemeral deployments, or concurrent writers across instances.
2. **Identity/security hardening:** salted scrypt hashing, password-strength checks, login-time legacy migration, OTP-log redaction, and single-process pilot rate limits are implemented. Public SaaS still needs shared gateway/Redis-backed abuse controls across replicas.
3. **Operational controls:** there is no centralised error monitoring, durable job queue, billing enforcement, verified backup/restore process, or disaster-recovery exercise.

## High-risk findings

- Pollers spawn only at process start; newly onboarded tenants require a restart.
- Multiple scripts and secondary backend modules still use `C:\Aradhana` paths and the default-tenant compatibility session.
- Debug/diagnostic endpoints now require an authenticated tenant session; public production should still remove them or restrict them to named operator roles.
- No centralised error monitoring, metrics, immutable external audit sink, backup verification, retention policy, or disaster-recovery exercise.
- No billing, subscription enforcement, tenant suspension, data export, account deletion, or support/admin workflow.
- Tenant-aware login now stores and sends a business slug through password, OTP, recovery, and authenticated requests. A formal custom-domain/subdomain strategy is still needed for public SaaS onboarding.
- The live reconciliation, review, escalation, owner-report, and audit-log screens now use tenant database-backed endpoints. The disconnected Prime extraction approval screen was removed from active navigation.

## Dependency and repository evidence

- Core and Prime Python requirement sets returned no known vulnerabilities in the July 2026 `pip-audit` database.
- The frontend Vite dependency was upgraded to 8.1.5 during this audit; `npm audit` now reports zero known vulnerabilities.
- No database, private key, certificate, or real `.env` file is tracked by Git. A local ignored `aradhana_dev.db` contains one user/session and must never be copied into a release image.
- A multi-stage Docker image and health-checked Compose service now provide a reproducible single-worker pilot topology with bind-mounted tenant data. It is intentionally bound to loopback and is not a public-SaaS topology.

## Controlled pilot gates

- [x] Scrypt hashing and legacy login-time migration covered by dedicated tests.
- [x] Remove/replace mock-backed live financial routes.
- [x] Make login and authenticated SPA calls tenant-aware.
- [ ] Limit the initial pilot to a controlled tenant cohort.
- [ ] Put the data directory on encrypted persistent storage with daily backups and a tested restore.
- [ ] Configure TLS and platform secret storage.
- [x] Add single-process pilot rate limits and require authentication for diagnostics.
- [x] Build a reproducible, health-checked single-host pilot container.
- [x] Resolve inherited test-contract failures and add dedicated password/rate-limit/security tests (148 passing).
- [ ] Build the frontend and verify login, OTP, dashboard, ingestion, review, logout, and backup recovery with non-production data.

## Public SaaS gates

- [x] Tenant-aware frontend using an explicit business identifier.
- [ ] Custom-domain/subdomain resolution and verified cross-tenant isolation tests.
- [ ] Managed transactional storage and object storage; no local JSON/session index as the authority.
- [ ] Separate web and worker processes with idempotent jobs and live tenant discovery.
- [ ] Centralised observability, alerting, audit retention, and incident response.
- [ ] Billing/subscription lifecycle, legal data-processing terms, tenant export/deletion, and support tooling.
- [ ] Load, concurrency, penetration, backup-restore, and disaster-recovery testing.

## Recommended deployment shape

Use a stateless FastAPI web service behind managed TLS, a managed relational database for tenant/session/control-plane data, encrypted object storage for invoices/evidence, and a durable queue with isolated ingestion workers. Windows-only Prime automation should remain an outbound edge agent installed at the tenant, authenticated with a rotatable per-tenant key.
