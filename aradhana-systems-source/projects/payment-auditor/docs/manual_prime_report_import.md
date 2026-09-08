# Manual Prime Report Import Instructions

## 1. Overview
As a transitionary measure, the Payment Auditor now supports manual imports of Excel reports exported directly from Prime. This replaces the bill-by-bill robotic extraction and ensures 100% data coverage from the source of truth.

## 2. Exporting from Prime
Daily, the user must export the following three reports from Prime:

| Report Name | Menu Path in Prime |
|-------------|-------------------|
| **GST Register** | Miscellaneous → GST Register |
| **Payment Mode Report** | Miscellaneous → Billwise Sale/Purc Detail (Payment Mode) |
| **Total Customer Report** | Miscellaneous → Total Customer Report |

### Export Guidelines:
- **Format:** Export as `.xls` or `.xlsx`. `.csv` is also supported.
- **Date Range:** Filter for the previous day (e.g., if today is June 1st, export for May 31st).

## 3. Importing into Auditor
1.  **Save Files:** Copy the exported Excel files into the following directory:
    `C:\Aradhana\PrimeExports\ManualReports`
2.  **Run Importer:** Execute the importer script:
    ```powershell
    python scripts/prime_report_importer.py
    ```
3.  **Verify Status:** Check the CLI output. It should report the number of records processed.
    - If no files are found, it will show: `NO_MANUAL_REPORT_FILES_FOUND`.

## 4. Verification on Dashboard
1.  Open the **Aradhana Payment Auditor** web interface.
2.  Navigate to the **Prime Extraction Review** page.
3.  The latest imported records from your Excel files will be visible here.
4.  **Action:** Review any records marked as `NEEDS_REVIEW` (e.g., due to payment total mismatches).

## 5. Support
For any issues with report detection or data joining, contact the system administrator and provide the log file:
`C:\Aradhana\PrimeExports\Logs\prime_report_import.log`
