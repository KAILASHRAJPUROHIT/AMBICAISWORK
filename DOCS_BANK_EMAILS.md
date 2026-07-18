# Bank Email Integration Checklist

Bank-email ingestion is configured per business in `businesses/<slug>/profile.json`; hosted tenants must never share IMAP credentials.

## Required alerts

- Immediate credit alerts for UPI, NEFT, IMPS, and RTGS.
- Cheque deposited, cleared, returned, and bounced notifications.
- Amount, reference/UTR, timestamp, bank/account identifier, and payer name when available.
- Daily or weekly statement exports for secondary human validation.

## Tenant configuration

Use the tenant profile's `imap` object (`server`, `port`, `user`, `password`, `folder`) and `alert_emails` list. Legacy `IMAP_USER`/`IMAP_PASS` variables apply only to the original single-business tool and must not be used for a shared SaaS deployment.

Use a dedicated read-only mailbox or folder where the bank supports it. Grant the minimum permission necessary, rotate credentials, and test failure/reconnect behaviour before enabling a production poller.

Never place real credentials in `profile.json` on an ephemeral or broadly accessible host. Before public SaaS launch, move secrets to an encrypted secret store and keep only secret references in the tenant profile.

