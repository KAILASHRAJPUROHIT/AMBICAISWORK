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

## 3. Geometric Proximity (Nearest Neighbor)
Once an anchor is found, the system identifies the "Input Field" (usually `ThunderRT6TextBox`) based on its relative coordinates.
- **Horizontal Match:** Look for a textbox to the immediate right of the label (same Y-coordinate, higher X-coordinate).
- **Vertical Match:** Look for a textbox directly below the label (same X-coordinate, higher Y-coordinate).
- **Grid Match:** In payment rows, identify headers and then find columns aligned with those headers.

## 4. Audit Evidence
For every field extracted, the system must log:
- `anchor_text`: The label used for discovery.
- `anchor_rect`: Coordinates of the label.
- `target_class`: The class of the matched input field.
- `target_rect`: Coordinates of the matched field.
- `extracted_value`: The text retrieved.

## 5. Validation Rules
Extraction is only valid if:
- `invoice_no` matches the pattern `SS/2026/` or similar.
- `invoice_total` is a positive number.
- `customer_name` is not empty.
- `SUM(payments)` matches `invoice_total` within 0.01 tolerance.
