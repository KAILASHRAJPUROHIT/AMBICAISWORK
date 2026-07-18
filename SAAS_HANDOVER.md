# AMBIC Payment Auditor — Handover (start here in a new session)

> **Launch status (2026-07-18):** This is a conversion checkpoint, not a production-readiness certificate. Public multi-tenant launch is blocked. Read `LAUNCH_READINESS_AUDIT.md` before making deployment or marketing claims.

**Location:** `D:\AI_PROJECTS\AMBIC-Payment-Auditor` — a completely standalone repo. The original
single-tenant tool for Aradhana Jewellers (`KAILASHRAJPUROHIT/Payment-Auditor`, live production,
real business) is **untouched**. Nothing in this conversion ever modified that repo or its
deployment.

**Git:** `https://github.com/KAILASHRAJPUROHIT/AMBIC-Payment-Auditor`, branch `main`, private.
11 commits at the time of the forensic audit, all pushed before the audit changes. Run `git log --oneline` for the
full list — every commit message is written as a standalone explanation of what changed and why,
so that log is itself a second source of truth for everything below.

---

## What this project is

A payment reconciliation and audit system: invoices come in (PDF watcher or manual), bank
payment evidence comes in (email/SMS), the two get automatically matched with a confidence score,
and anything uncertain goes to a human review queue. Built for jewellery/high-value retail where
cash, UPI, card, bank transfer, and cheque payments all need reconciling against scattered SMS
alerts and email confirmations, with role-based separation of duties (owner/accountant/staff).

This is the **third** AMBIC product, following the same pattern as the first two
(`AMBIC-SMARTQR`, `ambic-catalogue-studio`): take a working single-tenant tool built for one real
business, convert it into a multi-tenant SaaS product any business can sign up for. This one
started from a much more mature and much larger codebase than the other two — a live production
system with 50+ feature branches, real OTP-based auth, an RBAC model, and three live background
data-ingestion pollers — so the conversion was correspondingly bigger.

**Marketing page already exists** on ambicdigital.in (`src/lib/systems.ts`, slug
`payment-auditor`) describing this exact feature set — reconciliation engine, multi-channel
monitoring, review/escalation, audit trail. That page was written *before* any code existed for
it; this repo is what makes the claims on that page real.

---

## Architecture

### Per-tenant database — the central design decision

Every business gets its **own SQLite file**: `businesses/<slug>/data.db`. This is different from
how the other two AMBIC products do multi-tenancy (a shared database with a `tenant_slug` column
on every row). The choice was deliberate, made explicitly with the user before writing code:

> This app has ~50 API endpoints and a dozen tables of real financial data (bills, payments, bank
> alerts, audit logs). Row-scoping would mean auditing every single query in a financial-audit
> codebase for a missing `WHERE tenant_id = ?` — one missed filter is a real leak of one
> business's bank data into another's view. Per-tenant files make that whole bug class
> structurally impossible instead of relying on code review to catch it.

Practical effect: **the ~50 existing API endpoints in `review_api.py` needed almost no changes.**
Every route already went through one `get_db()` FastAPI dependency; making *that one function*
resolve the correct tenant and hand back an already-scoped session was enough. This is the
single most important thing to understand about this codebase's shape before touching it.

- **`backend/database.py`** — `get_session_factory(slug)` lazily creates and caches an
  `Engine`/`sessionmaker` per tenant, auto-provisioning that tenant's schema
  (`Base.metadata.create_all`) on first use. `DATABASE_URL` env var (documented in
  `.env.example` since before this conversion but never actually read by the original code — now
  fixed) forces every slug to the same database, used for test isolation.
  `SessionLocal`/`engine` still exist as **transitional compatibility shims** resolving to a
  "default tenant" (the sole registered business, or the `DATABASE_URL` override) — a handful of
  modules that haven't been converted to accept an explicit slug parameter yet still call these
  directly. See "What's genuinely NOT done" below.

- **`backend/business_registry.py`** — per-tenant JSON profile
  (`businesses/<slug>/profile.json`): business name, `alert_emails` list, `imap`/`smtp` config,
  `invoice_share_path`, `sms_inbox_path`. Mirrors the `tenant_profile.py`/`business_profile.py`
  pattern from the other two AMBIC products. Also owns the **global session-token → business-slug
  index** (`businesses/_session_index.json`) — this exists because a request carries only an
  opaque `X-Session-Token`, and *something* has to know which tenant's own `sessions` table to
  even look that token up in, before the per-tenant database can be resolved. Written at login
  (`create_user_session`), removed at logout.

- **`backend/tenant_context.py`** — `resolve_tenant_slug(request)`: checks `X-Business-Slug`
  header/`?business=` query param first (used for login, before any session exists), then the
  session-token index (authenticated requests), then falls back to the sole registered business
  if there's only one — same convenience fallback the other two AMBIC products use.

- **`backend/models.py`** — unchanged from the original single-tenant version. `User.employee_id`
  is still `unique=True` and that's *correct* now, not a bug — "unique within this one tenant's
  database file" is exactly what "globally unique" already meant when there was only one tenant.
  No `business_id` column exists anywhere, deliberately (see the per-tenant-file rationale above).

### Auth — real OTP, not a bolt-on

`backend/auth_service.py` (the real, production auth path — see "Dead code removed" below for the
one that *wasn't* real) implements employee-ID + password + email OTP, matching the original
README. Session tokens are random 32-char strings in each tenant's own `sessions` table, validated
per-request in `review_api.py`'s `security_middleware`. Roles: `ADMIN`, `OWNER`, `ACCOUNTANT`,
`DEVELOPER`, `STAFF`, `VIEWER` (`backend/rbac.py`) — `require_role()` in `review_api.py` does its
own string-list check per-route rather than going through `rbac.get_permissions`/`has_permission`
(those two functions are themselves unused in production — see the test-suite section).

**Password hashing was hardened during the forensic audit**: new/changed passwords use Werkzeug
`scrypt` hashes. Login still recognises the original 64-character SHA-256 format only long enough
to verify a legacy account and immediately replace it with a salted scrypt hash.
Owner setup and password reset now enforce a 12-character mixed-case/number policy, OTP values are
not written to verification logs, and auth/setup endpoints have in-process pilot rate limits.
Those limits are not a substitute for shared gateway/Redis enforcement in a scaled deployment.

### The three background pollers

All three were single-tenant (one hardcoded mailbox/share/inbox, one shared default-tenant DB
session) and are now genuinely multi-tenant — each spawns one thread pair/loop **per registered
business**, resolving that business's own config from its profile:

- **`backend/pdf_ingestion.py`** — filesystem watcher + periodic scan on
  `invoice_share_path` (falls back to a business-neutral local folder, was hardcoded to
  `\\PC2\AradhanaInvoicePDFs`). `_ingestion_status` is now `dict[slug, status]`.
- **`backend/email_poller.py`** — IMAP poll for bank-alert emails, reading each tenant's own
  `imap` config. `SMS_FORWARDER_SENDER`/`BANK_ALERT_FORWARDER` env vars replace two hardcoded
  personal/business email addresses that were baked directly into the classification rules.
- **`backend/sms_poller.py`** — reads `sms_inbox_path` per tenant. **Also had its simulation
  fallback removed entirely** — when unconfigured, the original code fabricated a fake ₹800
  "successful payment" and inserted it as a real `SMSAlert`/`BankAlert` row, indistinguishable
  from a genuine bank confirmation. For a payment-*auditing* product this was a real
  financial-integrity bug, not a demo convenience worth keeping.

**New businesses onboarded after the process starts need a restart** to have their pollers spawn
— none of the three watch `business_registry` live for newly-added tenants. Worth building a
live-reload path (or just periodic re-scan of `list_businesses()`) before this matters in
production with more than a handful of tenants signing up per day.

### Onboarding

`GET /setup` — a standalone HTML wizard (not part of the React SPA, so it ships with zero
frontend build step). Two steps: business name → first owner account (employee ID, name, email,
password). `POST /api/setup/save` creates the business profile and provisions its database file;
`POST /api/setup/create-owner` creates that tenant's first `User` row, always forced to
`role=OWNER`, and refuses a second call once one exists. Both endpoints are exempt from the
session-token auth gate (`PUBLIC_ENDPOINTS`) for the same reason `/api/auth/login` is — a
brand-new business has no token yet.

### What got deleted

- **`backend/main.py`** — a second, entirely unused FastAPI app (in-memory user/session store,
  `X-User-Role` header auth, toy `/users/`/`/bills/` endpoints). Never imported by `review_api.py`
  or started by any launcher script — confirmed dead before deleting.
- **`backend/auth.py`** — the in-memory auth scaffold `main.py` used. Also confirmed dead.
- **`tests/test_api_hardening.py`, `tests/test_api_routes.py`, `tests/test_auth.py`** — all three
  exclusively tested the two files above. Zero real coverage lost: `tests/test_rbac.py` already
  tests the real `rbac.py` module directly, and the real `auth_service.py` (used in production)
  had — and still has — no dedicated test file of its own. That's a real gap, not filled by this
  conversion; it's just not a *regression*, since it was never covered before either.

---

## Frontend

`frontend/src` is a Vite/React/TypeScript SPA. Hardcoded "Aradhana Auditor" branding was replaced
with generic "Payment Auditor" text. **Full per-tenant dynamic branding (fetched from each business's own
profile) was explicitly NOT built** — that's a real feature (an API endpoint returning the
current tenant's branding + a frontend fetch to render it), not a one-line fix, and was out of
scope for a correctness-focused conversion pass. Right now every tenant sees the same generic
"Payment Auditor" name in the UI regardless of their actual business name.

The login UI now requires (or pre-fills from `?business=`) an explicit business code. It stores
that slug and sends `X-Business-Slug` through login, OTP, resend, recovery, and authenticated API
calls. The obsolete session key and hardcoded loopback fetches were removed from active paths.
Public SaaS still needs a polished custom-domain/subdomain resolution strategy.

### Mock and disconnected UI/API paths

The mock financial routes were removed from `backend/api_routes.py`. Live reconciliation, review,
escalation, owner-report, and audit-log screens now call tenant database-backed endpoints in
`backend/review_api.py`. The inherited Prime extraction screen called a nonexistent endpoint and
presented a fake client-side approval action, so it was removed from active navigation.

---

## Running it locally

```
cd AMBIC-Payment-Auditor
pip install -r requirements.txt
cp .env.example .env          # fill in real values, or leave blank to explore /setup first
python -m backend.review_api  # or: uvicorn backend.review_api:app --reload
```

Visit `http://localhost:8000/setup` to create your first business + owner account. No `.env`
values are required just to explore the onboarding flow and the API — IMAP/SMTP only matter once
you want real OTP emails or real bank-alert ingestion to work.

For a controlled single-host pilot, `Dockerfile` builds the SPA and API together and
`docker-compose.yml` runs one worker with persistent `businesses/` and `invoice_inbox/` mounts.
It binds to `127.0.0.1:8000` and expects a separate TLS reverse proxy. Do not scale this Compose
service horizontally while SQLite and the JSON session index remain authoritative.

`requirements-prime-integration.txt` is separate and Windows-only (`pywinauto`, `pywin32`) — only
needed if a tenant uses the "Prime" desktop ERP integration (`scripts/prime_*.py`, UI-automation
driven, not an API). Not part of the core web app.

---

## Test suite

`pytest tests/` — **148 passing** as of the forensic audit. The suite went from *unable to
even collect* (the per-tenant database rewrite broke every test's import chain) to green. See
`tests/conftest.py`'s module docstring for the full isolation-seam mechanics (temp SQLite file via
`DATABASE_URL`, temp `business_registry.BUSINESSES_DIR`, one auto-registered `test-tenant`
business, explicit `backend.models` import ordering to avoid a real footgun around
`Base.metadata` being populated lazily).

Stale assertions were aligned with the implemented RBAC and machine-readable reconciliation
statuses. Authenticated production-filtering tests now create a real session and tenant mapping.
`tests/test_auth_passwords.py` covers salted scrypt hashes and legacy SHA-256 verification.

---

## What's genuinely NOT done

Ranked roughly by how much it matters before a second real business could safely use this:

1. **Production-grade storage and control plane** — SQLite tenant files and the JSON session index
   require a single persistent host and cannot support safe horizontal scaling.
2. **Rate limiting and abuse controls** — authentication, OTP, recovery, and setup endpoints need
   production throttling, lockout policy, and monitoring.
3. **Pollers don't live-reload new tenants** — process restart needed after onboarding a business
   for its PDF/email/SMS ingestion to actually start.
4. **A handful of modules still use the "default tenant" shim** rather than an explicit slug
   parameter: `reconciliation_orchestrator_v2.py`, `email_ingestion/orchestrator.py`, and most of
   `scripts/*.py` (migration/diagnostic/admin CLI tools). These only work correctly with exactly
   one business registered (or under the `DATABASE_URL` test override). Not blocking today since
   nothing calls them from a live multi-tenant request path, but worth converting before they're
   wired into anything customer-facing.
5. **No per-tenant dynamic branding** in the frontend (cosmetic, not a correctness issue).
6. **Postgres migration, S3/R2 object storage, Stripe/Razorpay billing, Sentry, custom
   subdomains** — same as the other two AMBIC products, all blocked on the user creating accounts
   with those services. Code can be written against placeholder config whenever credentials exist.

## What's genuinely done and verified

Every commit in this repo's history includes a real, working end-to-end verification (throwaway
scripts, not committed — described in each commit message): two separately-seeded tenants proven
isolated at the database level, a full login → OTP → verify → authenticated-request → logout
cycle over real HTTP through FastAPI's `TestClient`, a real onboarding flow creating a business
and logging its owner in immediately after, and each of the three pollers confirmed to actually
run scoped to the correct tenant (visible in the logs, not just "the code compiles"). This wasn't
a paper conversion — every claim above was exercised, not just written.
