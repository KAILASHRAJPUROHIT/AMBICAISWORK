# Payment Confirmation SLA Rules

## 1. Expected Bank Confirmation Timeline
The following table defines the allowed working days for bank confirmation based on the payment mode recorded on the invoice.

| Payment Mode | Allowed Working Days | Expected Confirmation |
|--------------|----------------------|-----------------------|
| **CASH**     | 0                    | Instant               |
| **UPI**      | 0                    | Same Working Day      |
| **IMPS**     | 0                    | Same Working Day      |
| **NEFT**     | 1                    | Next Working Day      |
| **RTGS**     | 1                    | Next Working Day      |
| **CARD**     | 1                    | Next Working Day      |
| **CHEQUE**   | 4                    | 4 Working Days        |

## 2. Bank Working Day Definition
Working days are calculated based on the Maharashtra Bank Holiday Calendar.

**Non-Working Days:**
- Every Sunday
- 2nd and 4th Saturday of every month
- Public Bank Holidays in Maharashtra

## 3. Pending Payment Aging (Color Status)
The aging of a pending payment is calculated as a percentage of the allowed working days.

| Elapsed % | Status Color | Meaning |
|-----------|--------------|---------|
| 0% - 49%  | **GREEN**    | Within expected window |
| 50% - 99% | **YELLOW**   | Approaching deadline |
| 100%+     | **RED**      | Overdue (Immediate Review) |

## 4. Workflows

### 4.1 Cash Workflow
- No bank confirmation required.
- Mark as `CASH_CONFIRMED` immediately.
- Status Color: **GREEN**.

### 4.2 Bank Confirmation Workflow
- If exact bank evidence is found (UTR/Amount/Mode match):
  - Move to **Payment Received** section.
  - Update status to `BANK_CONFIRMED`.
  - Status Color: **GREEN**.
  - Log immutable confirmation event.

### 4.3 Overdue Workflow
- If elapsed working days ≥ allowed working days:
  - Mark status as `RED` or `CHEQUE_PENDING_OVERDUE`.
  - Trigger manual review escalation.

## 5. Audit Logging Requirements
Every state change or aging update must create an immutable audit record:
- `PAYMENT_PENDING_CREATED`
- `PAYMENT_AGING_UPDATED`
- `PAYMENT_OVERDUE_ALERT`
- `PAYMENT_BANK_CONFIRMED`
- `PAYMENT_MANUAL_REVIEW`
