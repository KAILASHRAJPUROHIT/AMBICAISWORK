# AMBIC Payment Auditor — Financial Safety Rules

AI-assisted development may help write code, tests, documentation, parsers, and operator tooling. It must never be treated as payment evidence or an accounting authority.

The system and its operators must never:

- confirm an uncertain payment;
- delete or silently rewrite financial records;
- expose or reuse one tenant's credentials or records in another tenant;
- bypass accountant/owner review or role checks;
- auto-approve duplicate, delayed, reversed, bounced, split, cheque, or unclear cases;
- represent a mock, simulated, or generated event as a real bank confirmation.

Only exact, policy-approved matches backed by recorded source evidence may become Green. Every financial state change must create a tenant-scoped audit record containing the actor, timestamp, previous state, new state, and reason.

Production data, bank credentials, OTPs, session tokens, customer details, and invoice documents must never be placed in prompts, screenshots, fixtures, Git history, or public issue trackers.

