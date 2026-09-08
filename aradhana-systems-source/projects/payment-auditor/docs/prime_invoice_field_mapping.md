# Prime Invoice Field Mapping

Based on the probe conducted on 2026-05-31.

## Window Information
- **Title Contains**: `SHREE ARADHANA JEWELLERS`
- **MDI Form Class**: `ThunderRT6MDIForm`

## Main Invoice Controls (ThunderRT6TextBox)

| Field | Index | Example Value | Heuristic / Logic |
|-------|-------|---------------|-------------------|
| **Invoice No** | 25 | `SS/2026/196/` | Contains year pattern `/2026/` |
| **Invoice Date** | 10 | `01/05/2026` | Date format DD/MM/YYYY |
| **Customer Code** | 6 | `MJ0082` | Short alpha-numeric code |
| **Customer Name** | 4 | `Text2` | Likely field, but value in probe was placeholder |
| **Mobile / Address** | 20 | `...Mob. 8275980431` | Contains `.Mob.` prefix |
| **Invoice Total** | 29 | `12357.00` | Large decimal value, likely header total |
| **Item Taxable** | 54 | `4956.00` | Item-level taxable amount |
| **Item CGST** | 56 | `74.00` | Item-level CGST (1.5% in example) |
| **Item SGST** | 58 | `74.00` | Item-level SGST (1.5% in example) |
| **Item Total** | 61 | `5104.00` | Sum of item taxable and taxes |

## Payment Detail Sub-Form

The "Payment Detail" window is a dynamic `ThunderRT6FormDC` child form within the main MDI container.

- **Title Pattern:** `Sales Bill * GST Payment Detail`
- **Behavior:** Overlays the main invoice form when the `Pa&yment Detail` button is clicked.

### Key Discovery Headers
These `ThunderRT6CommandButton` controls help define the grid columns:
- `Card Amt.`
- `ChqNo.`
- `Drawn On`
- `Against Voucher`

### Extraction Strategy
- Payment rows are represented by sequential `ThunderRT6TextBox` controls.
- **Order Preservation:** Rows must be extracted in the order they appear in the control tree to maintain accounting integrity.
- **Dynamic Indices:** Indices for these fields appear to be dynamic (offset from the parent form's first control). Mapping must be validated across multiple invoices (minimum 5) before finalizing static indices.

## Item Grid Context
Indices 34-63 appear to correspond to the active item row in the invoice grid:
- [34] `Product`
- [41] `SILVER MURTI` (Product Name)
- [44] `1` (Quantity)
- [46] `17.700` (Weight)
- [49] `280.00` (Rate)

## Key Command Buttons
- [23] `Invoice Amount`
- [24] `Taxable`
- [35] `Total Payable`
- [54] `Pa&yment Detail` (Note: Index shifted to 54 in diff probe)
