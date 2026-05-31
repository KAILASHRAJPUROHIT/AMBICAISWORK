# Prime Extraction Validation Report

**Date:** 2026-05-31
**Environment:** Prime (win32)
**Strategy:** Refined Label-Anchored + Visibility Guards
**Overall Result:** FAIL (Data Presence/Mapping Issue)

## Summary
| Test Case | Scenario | Status | Note |
|-----------|----------|--------|------|
| 1 | Cash Only | FAIL | Anchors matched empty textboxes or search fields |
| 2 | Mixed Payment | UNTESTED | Blocked by Test Case 1 |
| 3 | Old Gold | UNTESTED | Blocked by Test Case 1 |

---

## Test Case 1: Cash Only (Invoice SS/2026/201/)

### Fix Verification
- **Form Scoping:** PASS. Extractor successfully differentiated between "Payment Detail", "Register", and "Sales Bill" forms.
- **Visibility Guard:** PASS. System detected minimized state and attempted restore; coordinates are now positive.

### Comparison: Prime Screen vs. Extracted JSON
| Field | Prime Screen | Extracted JSON | Match |
|-------|--------------|----------------|-------|
| **Invoice No** | `SS/2026/201/` | `""` | FAIL |
| **Invoice Date** | `01/05/2026` | `""` | FAIL |
| **Customer Name** | `Text2` | `"GST"` | FAIL (Matched search field) |
| **Customer Code** | `HK0048` | `""` | FAIL |
| **Invoice Total** | `9352.00` | `""` | FAIL |

### Technical Mismatch Details
- **Anchor Ambiguity:** Anchors like "A/c Name" were matched to global search fields (containing "GST") instead of the specific invoice field.
- **Proximity Weighting:** The proximity logic needs to be much stricter about horizontal alignment and exclusion of "Control Header" textboxes.
- **MDI Context:** Labels found in the MDI parent are successfully being used to anchor textboxes in the child form, but the "nearest" neighbor is often a header field rather than the data field.

## Prime Extraction MVP Status
**STATUS:** **FAIL**

**Required Refinements:**
1. Refine `find_nearest_textbox` to prefer textboxes with numeric/pattern-matched data (e.g., date pattern for Date field).
2. Explicitly exclude known "Header/Search" textboxes by coordinate range or class.
3. Validate against a screen where an invoice is explicitly "Active" and "Loaded".
