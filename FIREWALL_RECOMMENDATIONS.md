# Network and Deployment Security Recommendations

AMBIC Payment Auditor now supports hosted multi-tenant operation; it is no longer protected by a LAN-only application gate. Network controls must match the deployment model.

## Hosted application

- Terminate TLS at a managed reverse proxy and redirect HTTP to HTTPS.
- Expose only ports 80/443 publicly; keep databases, object storage, admin diagnostics, and poller control surfaces private.
- Restrict setup/onboarding after the intended tenant-creation flow is established.
- Apply rate limits to login, OTP, password-reset, setup, and ingestion-trigger endpoints.
- Store SMTP/IMAP credentials in an encrypted secret manager, not tenant JSON on disk.
- Disable or authenticate `/debug/*` and operational status routes before launch.
- Use centralised audit logs, error monitoring, backups, and alerting with tenant identifiers but no raw financial evidence.

## Local edge integrations

Prime desktop automation, SMB invoice shares, and SMS relays should run on a business-controlled Windows edge machine. Use outbound-only connections to the hosted service where possible. Do not expose SMB, the Prime application, or local relay ports to the internet.

If remote administration is required, use a managed VPN/zero-trust tunnel with MFA. Do not create public port-forwarding rules to the Windows host.

## Pilot minimum

For a single-business pilot, bind the local service to an explicit trusted interface, use TLS or a trusted private tunnel, rotate all default credentials, and verify that backups and restore procedures work before processing real invoices.

