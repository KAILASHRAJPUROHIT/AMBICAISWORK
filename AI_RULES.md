# Aradhana Payment Auditor - AI Rules

AI may help write code, tests, documentation, and structure.

AI must never:
- confirm uncertain payments
- delete financial records
- access live bank credentials
- bypass accountant review
- auto-approve risky entries
- silently modify financial records

Only exact verified matches may become Green.

Yellow, Orange, Red, duplicate, delayed, bounced, split, or unclear cases must go to human review.

All financial changes must create audit logs.
