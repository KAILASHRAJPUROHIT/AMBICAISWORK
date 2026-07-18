# AMBIC SmartQR — Forensic SaaS Launch Audit

**Assessment:** NO-GO for unattended commercial rollout. A supervised one-tenant pilot is possible after the pilot gates are complete.

## Critical/high findings

1. A packaged/signed installer does not exist. The Task Scheduler scripts now use the repository-local `.venv` interpreter and fail with setup guidance instead of relying on a developer-specific path.
2. The agent's old pinned dependencies contained 46 known vulnerabilities across Requests, python-dotenv, pypdf, and Pillow. They were upgraded during this audit; a follow-up `pip-audit` reported no known vulnerabilities.
3. A durable local SQLite execution ledger now blocks ambiguous reprints. The cloud service still lacks a formal lease/operator recovery workflow for stuck jobs.
4. SQLite, tenant JSON profiles, and local media are unsuitable for ephemeral or horizontally scaled cloud hosting.
5. There is no billing, subscription suspension, central error monitoring, queue metrics, operator console for stuck jobs, or tested disaster recovery.

## Positive evidence

- Cloud Python dependencies returned no known vulnerabilities in the July 2026 `pip-audit` database.
- Tenant slug filtering is pervasive in queue/staff/admin queries.
- Agent endpoints authenticate with tenant-specific `X-Agent-Key`.
- Media downloads use tenant resolution and per-job access tokens.
- No real `.env`, database, key, or certificate is tracked by Git.

## Pilot gates

- [ ] Re-audit the upgraded agent dependencies in CI on supported Python 3.11/3.12.
- [x] Replace the hardcoded interpreter path with the repository-local virtual environment.
- [ ] Add a cloud-side job lease and explicit operator stuck-job recovery UI.
- [ ] Test one print under normal operation and controlled crashes at each lifecycle stage.
- [ ] Put the server database/media on encrypted persistent storage and test restore.
- [ ] Add rate limits, central logs, queue alerts, secret rotation, and documented operator recovery.

## SaaS gates

- [ ] Managed database and object storage with migrations and retention.
- [ ] Stateless web instances and a shared durable queue.
- [ ] Billing/subscription lifecycle and tenant suspension/export/deletion.
- [ ] Signed agent releases, update channel, device inventory, key rotation, and revocation.
- [ ] Supported printer/driver matrix and remote diagnostics that do not expose customer documents.
- [ ] Load, isolation, security, and disaster-recovery tests.
