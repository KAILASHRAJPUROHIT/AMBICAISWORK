# Shared AI Development and Audit Rules

These rules apply to Codex, Gemini, Continue, and any AI assistant working on the Aradhana Payment Auditor codebase.

## Branch and Change Control

- One feature = one branch.
- Do not modify backend/frontend business logic in this branch.
- No silent edits.
- Show affected files before editing.
- Show exact diff before applying.
- Show rollback command before or with every commit.
- Run tests before commit.
- Every branch must end with test evidence, commit hash, and rollback command.

## Payment Safety Hardwalls

- Never auto-confirm uncertain payments.
- CASH auto-confirm only.
- ADVANCE requires accountant review.
- CUST PURCHASE / OLD_GOLD_EXCHANGE requires accountant review.
- No proof for CASH / ADVANCE / CUST PURCHASE.
- Never use bill.reference_no as payment proof.
- Never create dummy Payment objects.

## Data Integrity and Auditability

- No hard deletes.
- Preserve audit trail.
- Never reintroduce removed schema fields like BankAlert.bill_id or SMSAlert.bill_id.

## Required Closeout

- Test evidence must be recorded before commit.
- Commit hash must be reported after commit.
- Rollback command must be reported after commit.
- Standard rollback command: `git revert <commit-hash>`.
