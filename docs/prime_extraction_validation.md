# Prime Extraction Validation Report

**Date:** 2026-05-31
**Environment:** Prime (win32)
**Strategy:** Deterministic Pattern Detection (MVP Refactoring)
**Overall Result:** FAIL (Environment/State Issue)

## Summary
| Test Case | Scenario | Status | Note |
|-----------|----------|--------|------|
| 1 | Cash Only | FAIL | No textboxes detected in current session |
| 2 | Mixed Payment | UNTESTED | Blocked |
| 3 | Old Gold | UNTESTED | Blocked |

---

## Technical Blockers
- **Control Visibility:** Recent probes (`scripts/diag_windows.py` and `scripts/prime_payment_detail_probe.py`) show 0 textboxes being returned by `pywinauto` for the `FA.exe` process. 
- **32-bit vs 64-bit:** A warning was detected indicating that 32-bit `FA.exe` should be automated with 32-bit Python. Using 64-bit Python may cause intermittent invisibility of legacy VB6 controls.
- **Form State:** Exhaustive searches for `ThunderRT6FormDC` currently return empty titles, suggesting forms may be minimized to the MDI taskbar or closed.

## MVP Pivot: Deterministic Patterns
I have refactored the extraction logic to move away from brittle label proximity. The new strategy:
1.  **Exhaustive Collection:** Pool all non-empty textboxes from the entire process.
2.  **Pattern Match:** Use regex to identify `invoice_no` (e.g., `SS/2026/...`), `date`, and `mobile`.
3.  **Heuristics:** Identify `invoice_total` as the largest numeric value in the form scope.

## Status: NEEDS REVIEW
The code is implemented and much more robust, but it requires the target controls to be visible to the automation backend. 

**Recommended Action:**
1. Ensure Prime has an invoice explicitly open and maximized.
2. If possible, use a 32-bit Python environment for the extractor to resolve address-space visibility issues with legacy VB6 controls.
