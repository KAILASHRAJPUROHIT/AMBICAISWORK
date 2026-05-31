# Prime Control Anchor Strategy

## Overview
To ensure robust extraction across dynamic UI states in Prime (VB6), we are moving from global indices to a label-anchored detection strategy.

## 1. Form Scoping
All extraction must be scoped to an active `ThunderRT6FormDC`.
- **Target Form:** The sub-form containing the data (e.g., "Sales Bill Silver GST", "Payment Detail").
- **Safety:** Prevents "ghost" data from background forms or the MDI container from contaminating extraction.

## 2. Anchor Identification
Labels in Prime are typically implemented as `ThunderRT6CommandButton` or `Static` controls.
- **Strategy:** Find a control with the exact (or partial) text of the field label.
- **Example Anchors:**
  - `Vch.No.` or `Invoice No`
  - `A/c Name`
  - `Mobile`
  - `Invoice Amount`
  - `Total Payable`

## 3. Deterministic Pattern Detection (MVP Refined)
Instead of relying solely on label proximity (which is sensitive to layout shifts and search field overlaps), the MVP now uses a pattern-first detection strategy for the header.
- **Invoice No:** Regex matching `(SG|SS|S1|S2|S4|S5)/\d{4}/\d+/`.
- **Date:** Regex matching `\d{2}/\d{2}/\d{4}`.
- **Mobile:** Search for `.Mob.` marker or 10-digit numeric sequence.
- **Amounts:** Non-zero decimal values are pooled; the largest is heuristically tagged as `invoice_total`.

## 4. Spatial Grouping (Payment Rows)
Spatial grouping by Y-coordinate remains the preferred strategy for multi-source payment rows as it preserves accounting row integrity.

## 5. Validation Rules
Extraction is only valid if:
- `invoice_no` matches the pattern `SS/2026/` or similar.
- `invoice_total` is a positive number.
- `customer_name` is not empty.
- `SUM(payments)` matches `invoice_total` within 0.01 tolerance.
