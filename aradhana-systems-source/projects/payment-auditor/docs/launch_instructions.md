# Aradhana Payment Auditor: Launch Instructions

This guide explains how to start the application for daily use.

## Quick Start (One-Click)

The project includes two launcher scripts at the root directory:

### 1. `start_aradhana_auditor.bat` (Recommended)
Use this for daily monitoring.
*   **What it does:** Starts the Backend API and Frontend UI, then opens your browser to the dashboard.
*   **How to use:** Double-click the file.

### 2. `run_import_and_launch.bat` (After New Reports)
Use this after you have placed new Excel files in `C:\Aradhana\PrimeExports\ManualReports`.
*   **What it does:** Imports the data from your Excel files first, then launches the application.
*   **How to use:** Double-click the file.

---

## Important Configuration

### ⚠️ Backend API Warning
The system uses `backend.review_api:app` for live production data.
**DO NOT** attempt to use `backend.main:app` for the live dashboard; it is a legacy endpoint and will show incorrect data.

### 🏠 File Paths
Ensure your Prime reports are exported to:
`C:\Aradhana\PrimeExports\ManualReports`

The system generates the consolidated database at:
`C:\Aradhana\PrimeExports\JSON\prime_report_import.json`

---

## Desktop Shortcut (Optional)

To make it even easier to launch from your desktop:
1.  Right-click `start_aradhana_auditor.bat`.
2.  Select **Send to** > **Desktop (create shortcut)**.
3.  Rename the shortcut to "Aradhana Auditor".

---

## Troubleshooting

If the application fails to start:
1.  Open a terminal in the project folder.
2.  Run the health check:
    ```bash
    py -3.11 scripts\health_check_launch.py
    ```
3.  If "Backend API" shows FAILED, ensure no other program is using Port 8000.
4.  If "Frontend UI" shows FAILED, ensure no other program is using Port 5173.
