# AMBIC SmartQR — Legal and Compliance Baseline

**Policy version:** 2026-07-18  
**Public product terms:** https://ambicdigital.in/legal/smartqr-schedule  
**Privacy:** https://ambicdigital.in/privacy  
**Acceptable use:** https://ambicdigital.in/legal/acceptable-use  
**Complaints:** https://ambicdigital.in/legal/copyright-and-complaints

This repository is controlled-pilot software and is not approved for unattended public SaaS. Legal text does not override the security and operational blockers in `LAUNCH_READINESS_AUDIT.md`.

## Mandatory pilot records

- A work order identifying the tenant, operator, printer/driver, location and supported document types.
- A data-processing schedule naming the customer as the party responsible for notices and permission to collect/print files.
- A stated live print-file retention window, retry window, backup behaviour and deletion owner.
- An authorised-user and agent-device register, including key issue, rotation and revocation dates.
- A test record for normal print, paper/ink failure, network loss, agent crash and stuck-job recovery.
- A signed acknowledgement that automatic crop/orientation and job status require human/physical verification.

## Deployment controls

- Do not expose `/setup` publicly in its current form. Provision tenants only through a trusted operator until authenticated provisioning is implemented.
- Do not return or display tenant secrets after initial secure provisioning.
- Require clear permission language before file upload or social-handle collection.
- Show links to the current privacy, acceptable-use and SmartQR schedule at upload and administration surfaces.
- Keep customer print files private and short-lived; do not treat the queue as document storage.
- Preserve only the minimum job/security evidence needed for support and disputes.
- Protect the physical output tray and local Windows agent; the cloud boundary alone does not protect printed paper.

## Prohibited initial uses

- Government-ID verification, medical, legal-case or highly sensitive records without a separately designed and approved deployment.
- Forged documents, unlawful monitoring, covert profiling or printing without the data subject/customer's authority.
- Public anonymous uploads, self-service tenant creation or multi-location rollout before the launch audit gates pass.

## Incident and complaint handling

Security, privacy and rights complaints go to `ambicdigital@gmail.com`. Preserve the affected job ID, tenant, timestamps and relevant access logs without copying unnecessary document contents. Restrict the job or tenant while investigating. Applicable statutory and emergency timelines take precedence over ordinary support targets.
