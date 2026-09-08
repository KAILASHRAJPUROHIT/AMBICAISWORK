# Milestone: Payment Proof Hardwall Partial Implementation

This milestone represents the completion of several critical patches related to payment proof attribution and display, aligning with the "P0 PAYMENT MODE + PROOF ATTRIBUTION HARDWALL" mandate.

## Completed Patches:

1.  **Patch 1 (Revert `bill.reference_no` nullification):**
    *   **File:** `backend/pdf_ingestion.py`
    *   **Description:** Restored `bill.reference_no` to be populated directly from `invoice_data["reference_no"]`, ensuring mixed-mode invoices retain valid bill-level UTRs. This corrected an over-correction that would have nullified valid references.

2.  **Patch 2a (Extract `p["reference"]` in `parse_pdf`):**
    *   **File:** `backend/pdf_ingestion.py`
    *   **Description:** Modified the `parse_pdf` function to extract `reference` numbers (e.g., UTRs, TxnIDs) from raw PDF payment lines and store them in the `payments` list as `p["reference"]`. Crucially, `payment_reference` is explicitly set to `None` for non-electronic modes (`CASH`, `ADVANCE`, `OLD_GOLD_EXCHANGE`, `BALANCE`, `UNKNOWN`) during parsing.

3.  **Patch 2 (Enforce `Payment.utr_reference`/`cheque_number` rules):**
    *   **File:** `backend/pdf_ingestion.py`
    *   **Description:** Modified `Payment` object creation to strictly enforce UTR/cheque_number rules:
        *   `Payment.utr_reference` is `None` for `CASH`, `ADVANCE`, `OLD_GOLD_EXCHANGE`, `CHEQUE`. For `BANK_TRANSFER`, it uses `new_bill.reference_no`; for other electronic modes, it uses `p.get("reference")`.
        *   `Payment.cheque_number` is `None` unless `p["mode"] == "CHEQUE"`, in which case it uses `p.get("reference")`.

4.  **Patch 3 (`calculate_payment_proof_status` `payment_utr` logic):**
    *   **File:** `backend/reconciliation/logic.py`
    *   **Description:** Refined `payment_utr` determination within `calculate_payment_proof_status`. For electronic modes, it uses `payment.utr_reference` only (no fallback to `bill.reference_no`). For `CASH`, `ADVANCE`, `OLD_GOLD_EXCHANGE`, `payment_utr` is explicitly `None`, preventing proof matching.

5.  **Patch (Fix `find_payment_evidence` display leakage):**
    *   **File:** `backend/review_api.py`
    *   **Description:** Corrected the `reference` displayed by `find_payment_evidence`. For `CASH`, `ADVANCE`, `OLD_GOLD_EXCHANGE`, `display_reference` is now `None`. For electronic modes, it uses `payment.utr_reference` directly, with no fallback to `bill.reference_no` for display.

## Affected Files:

*   `backend/pdf_ingestion.py`
*   `backend/reconciliation/logic.py`
*   `backend/review_api.py`
*   `HANDOFF_PAYMENT_HARDWALL.md` (new file)

## Remaining Work:

1.  **Phase 3, Step 2: Refactor Fallback Payment Logic in `review_api.py`:**
    *   **Goal:** Replace the manually duplicated proof logic in the fallback loop of `get_open_reconciliation_real` with calls to the shared helper.
    *   **Patch 4 (Deferred):** Modify `calculate_payment_proof_status` to accept `Union[Payment, PaymentInputDict]` (a simple dict) as its `payment` argument. This is crucial to allow the fallback loop to call the shared helper without creating dummy ORM objects or duplicating logic.
    *   **Action:** Implement the fallback loop using this flexible input for `calculate_payment_proof_status`.
2.  **Integrate overall Bill Confidence:** Update the overall bill confidence in `get_open_reconciliation_real` (currently `reconciliation_confidence`) to aggregate from the granular `payment_breakdown` entries.
3.  **Dashboard Integration:** Update dashboard endpoints (`/api/dashboard/live` or `/api/prime/dashboard/stats`) to use the new confidence calculation from the shared helper.
4.  **Testing:** Implement all required new test cases.

## Known Risks:

*   **Parser Robustness:** The regex for extracting `payment_reference` in `pdf_ingestion.py` (Patch 2a) is generic. It might not capture all variations of references or could misinterpret other text as references. This is a general risk with regex-based parsing.
*   **Fallback Logic Complexity:** Reimplementing the fallback logic (when Patch 4 is applied) correctly to map existing `bill.cash_received`, `bill.bank_received`, `bill.card_received` to the `PaymentInputDict` structure requires careful attention.
*   **Performance:** Introducing more intricate logic and loops in core reconciliation paths could have minor performance implications, though likely negligible.

## `RTGS_OR_CHEQUE` Rule:

*   The invoice parser (`pdf_ingestion.py`) assigns `RTGS_OR_CHEQUE` mode if "RTGS", "CHEQUE", or "CHQ" keywords are found.
*   There is *no* auto-classification into `CHEQUE` based on invoice text.
*   `RTGS_OR_CHEQUE` is treated as ambiguous/electronic until bank evidence (e.g., from `BankAlert`) confirms the nature of the payment.
*   `Payment.cheque_number` is only populated if the `Payment.mode` is exactly `CHEQUE` (which currently doesn't happen via parsing) and `p.get("reference")` provides a value.
*   Cheque ageing will start only from explicit bank/deposit evidence, not from invoice text.

## Rollback Command:

`git revert <commit_hash>` (where `<commit_hash>` will be the hash of the commit created in this milestone).

## Tests Still Required:

*   `cash with bill.reference_no does not inherit UTR`
*   `cash auto-confirms received`
*   `cash does not show SMS proof`
*   `advance does not auto-confirm`
*   `advance does not inherit reference`
*   `cust purchase (OLD_GOLD_EXCHANGE) does not auto-confirm`
*   `cust purchase (OLD_GOLD_EXCHANGE) does not inherit reference`
*   `UPI matching amount+UTR shows proof`
*   `UPI amount mismatch does not show proof`
*   `dashboard and reconciliation confidence values match for same payment`
*   **New test for Patch 2a:** Invoice PDF with mixed modes (CASH and UPI with UTR) parses correctly, verifying `p["reference"]` population.
*   **New test for Patch 2:** `Payment` objects created from mixed-mode invoice correctly have `utr_reference=None` for CASH and `utr_reference=<UTR>` for UPI.
*   **New test for `RTGS_OR_CHEQUE`:** Ensure payments classified as `RTGS_OR_CHEQUE` are handled as electronic modes for proof matching but do not get a `cheque_number` from parsing.