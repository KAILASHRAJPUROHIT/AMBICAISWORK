# Bank Email Operational Checklist

To ensure deterministic reconciliation, all banks should be configured to send the following alerts to the registered email address:

1.  **Transaction Alerts**:
    *   Immediate email for every credit (UPI, NEFT, IMPS, RTGS).
    *   Email should contain: Amount, UTR/Reference Number, and Sender Name if available.

2.  **Cheque Alerts**:
    *   Alert when a cheque is deposited or sent for clearing.
    *   Alert when a cheque is cleared (Realized).
    *   Alert when a cheque is returned or bounced (with reason).

3.  **Account Statements**:
    *   Daily or weekly automated statements in PDF or Excel format for secondary validation.

## Technical Configuration
*   Use environment variables for IMAP credentials (`IMAP_USER`, `IMAP_PASS`).
*   Ensure the auditor laptop has read access to `Z:\Aradhana\InvoicePDFs`.
*   Maintain `Z:` drive mapping even after restarts.
