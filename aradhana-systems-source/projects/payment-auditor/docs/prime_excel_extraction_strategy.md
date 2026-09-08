# Prime Excel Extraction Strategy Report

## 1. Overview
The Prime extraction pipeline has been updated to prioritize the **Billwise Sale/Purc Detail (Payment Mode)** report. This strategy uses automated Excel exports to retrieve structured settlement data, which is more reliable than direct UI scraping of the GST register.

## 2. Implementation
- **Exporter:** `scripts/prime_payment_mode_report_exporter.py`
  - Automates navigation to `Miscellaneous -> Billwise Sale/Purc Detail (Payment Mode)`.
  - Uses direct Win32 `WM_COMMAND` (ID: 245) to bypass menu navigation fragility.
  - Automatically sets yesterday's date filter and triggers Excel export.
- **Parser:** `scripts/prime_excel_parser.py`
  - Uses `pandas` and `xlrd` in a 64-bit environment to transform the `.xls` export into a reconciliation-ready JSON (`prime_sales_report.json`).

## 3. Analysis

### Can this report replace GST Register extraction?
**Yes.** 
The Payment Mode report is superior for reconciliation because:
1. It provides an explicit breakdown of **Cash, Bank, Card, Advance, and Balance** amounts per invoice.
2. It captures the **settlement state** directly from the accounting entries.
3. Excel-based extraction eliminates the "index instability" and "visibility" issues encountered with the VB6 UI controls.

### What fields remain missing?
While the report is excellent for settlement, some data points are better retrieved from the GST Register or individual invoices:
- **Detailed HSN/SAC Codes:** Usually only available in GST-specific reports.
- **Mobile Numbers:** Often truncated or formatted as "Mob. XXX..." in summary reports.
- **Product Lines:** If an invoice has 10+ items, the Excel report might only show a summary or the first few items depending on the report configuration.

## 4. Operational Status
The system is now capable of a high-integrity validation run using the Excel-first approach. UI-based invoice scraping remains available as a surgical fallback for missing mobile numbers.
