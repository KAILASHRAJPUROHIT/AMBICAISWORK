# AMBIC DIGITAL Payment Notifier

Standalone backend for the bank-activity desktop popup (`AradhanaBankActivityNotifier`)
and its Android SMS-relay companion. Extracted from `payment-auditor` on 2026-09-12 —
this service has no reconciliation, Bill/Payment, or Prime ERP code at all; it exists
only to turn incoming bank SMS/email alerts into the `/api/bank-activity` feed the
notifier popup polls.

## Data flow

```
bank SMS/email → IMAP mailbox (email_poller.py)
Android relay app → POST /api/sms-relay/ingest
                              ↓
                        SMSAlert table
                              ↓
                   GET /api/bank-activity  →  desktop popup
```

## Auth

Two separate shared tokens (headers), replacing the old LAN-only IP check that
can't work now this is public on AWS:
- `X-Notifier-Token` — the desktop popup, read-only + copy-state/correction writes.
- `X-Relay-Token` — the Android SMS relay, write-only via `/api/sms-relay/ingest`.

Kept separate so a leaked notifier token can't be used to inject fake transactions.

## Deploy

See `deployment/aws/` — Docker Compose, joins the shared `ambic-shared` network so
the existing Caddy instance (from `qr-print-server/deployment/aws`) can front it.
Copy `.env.example` to `.env` and fill in real IMAP credentials + generated tokens.

## Known gap

The notifier's self-update mechanism (`/api/bank-activity/notifier-release*` in the
original app) was not ported — no release EXEs live here yet. The desktop app will
need its `settings.json` `server_url` repointed at this service manually, and the
Android relay app needs its upload target changed from the old file-share write to
`POST /api/sms-relay/ingest`. Both are follow-up work, not done as part of the
backend migration itself.
