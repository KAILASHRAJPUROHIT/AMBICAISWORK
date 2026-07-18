# AMBIC Payment Auditor — Legal and Compliance Baseline

**Policy version:** 2026-07-18  
**Public product terms:** https://ambicdigital.in/legal/payment-auditor-schedule  
**Privacy:** https://ambicdigital.in/privacy  
**Data processing:** https://ambicdigital.in/legal/data-processing-addendum  
**Complaints:** https://ambicdigital.in/legal/copyright-and-complaints

This repository is evaluation/tightly controlled pilot software and is not approved for public multi-tenant SaaS. Legal wording does not cure the authorisation, spoofable-actor, storage, secret, observability and recovery blockers in `LAUNCH_READINESS_AUDIT.md`.

## Decision-support boundary

Payment Auditor is not a bank, payment processor, accountant, statutory auditor or fraud guarantee. Automated matches and confidence scores are indicators. Authorised personnel must review uncertain, exceptional, conflicting and high-value evidence before fulfilment, refund, accounting, disciplinary or enforcement action.

## Mandatory pilot records

- Signed work order identifying the controlled tenant, users, roles, ingestion channels and authorised integrations.
- Data-processing schedule listing invoices, customer/staff data, payment evidence, bank/email/SMS sources, locations and retention.
- Named actor mapping; never accept a client-supplied approver/accountant ID as authoritative without deriving it from the authenticated session.
- Mailbox/ERP/network-share credential register with issue, rotation and revocation dates.
- Backup and tested-restore evidence, incident contacts and an escalation matrix.
- Customer acknowledgement that original bank, ERP, invoice and communication evidence remains authoritative and independently retained.

## Prohibited launch conditions

- No public self-service setup or unattended multi-tenant onboarding.
- No real financial data on ephemeral storage, public test systems or developer laptops copied outside the controlled business environment.
- No horizontal scaling while SQLite tenant files and the JSON session index remain authoritative.
- No claim that application logs are immutable, that every fraud/error will be detected, or that a match replaces professional review.
- No production use until the broken role-dependency pattern and spoofable actor attribution are repaired and runtime-tested.

## Retention and access

The customer determines lawful financial-record retention and authorised roles. Ambic must minimise copied evidence, protect credentials, log security-relevant access and support verified export/deletion subject to accounting, investigation, tax and dispute requirements. Deletion must not silently destroy evidence the customer is legally required to retain.

## Incidents and complaints

Report security, privacy, reconciliation and access-control incidents to `ambicdigital@gmail.com`. Preserve source evidence, timestamps, tenant and authenticated actor records. Do not alter the original bank/ERP evidence while investigating. Restrict compromised credentials and affected access immediately.
