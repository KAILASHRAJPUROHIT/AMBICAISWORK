# Aradhana Payment Auditor - Project Instructions

## 1. Prime Invoice Extraction Rules

### 1.1 Multi-Source Payments
Prime invoices may be settled using multiple payment sources simultaneously. The extractor MUST NOT assume a single payment source.

- **Extraction:** Extract ALL payment rows.
- **Order:** Preserve payment row order.
- **Granularity:** Never collapse or overwrite multiple payment rows. Store each source independently.

**Supported Payment Modes:**
- `ADVANCE`
- `BALANCE`
- `CASH`
- `CARD`
- `UPI`
- `IMPS`
- `NEFT`
- `RTGS_OR_CHEQUE`
- `OLD_GOLD_EXCHANGE`

### 1.2 Data Structure (JSON)
```json
{
  "invoice_no": "",
  "invoice_total": 0,
  "payment_rows": [
    {
      "payment_type": "",
      "payment_mode": "",
      "amount": 0,
      "reference": "",
      "bank_name": "",
      "narration": ""
    }
  ]
}
```

### 1.3 Validation & Reconciliation
- **Total Validation:** `Invoice Total` must equal `SUM(ALL_PAYMENT_ROWS)`.
  - Mismatch Status: `RED`, Reason: `PAYMENT_TOTAL_MISMATCH`.
- **Advance/Balance:** Treat `ADVANCE` and `BALANCE` as separate accounting events. Do not merge.
- **Old Gold:** `OLD_GOLD_EXCHANGE` is a separate event; do not treat as cash.
- **Bank Matching:** Only bank-originated rows (`UPI`, `IMPS`, `NEFT`, `RTGS_OR_CHEQUE`, `CARD`) participate in bank matching.
  - Do NOT match: `CASH`, `ADVANCE`, `BALANCE`, `OLD_GOLD_EXCHANGE`.
  - **Auto-Confirmation:** Never auto-confirm unless all bank-originated rows are verified.

## 2. Engineering Standards
- **UI Automation:** Use `pywinauto` with `win32` backend for Prime (legacy VB6 controls).
- **Safety:** Read-only probes by default. No clicks/typing/saves unless explicitly requested.
- **Compliance:** Follow all rules in `AI_RULES.md`.
