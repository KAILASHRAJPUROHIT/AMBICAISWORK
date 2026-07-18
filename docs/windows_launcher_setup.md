# Aradhana Payment Auditor - Windows Launcher Setup

This document describes how to build and use the single-window launcher for the Aradhana Payment Auditor.

## 1. Prerequisites

- Python 3.11
- Node.js & npm (for building the frontend)
- `pip install pyinstaller pywin32`

## 2. Building the EXE

To build the single EXE:

```powershell
python scripts/build_launcher_exe.py
```

This script will:
1. Build the React frontend (`npm run build`).
2. Bundle the Backend, Frontend, and Launcher into `dist/AradhanaPaymentAuditor.exe`.

## 3. Usage

- **Launch:** Double-click `AradhanaPaymentAuditor.exe`. It will start the backend, all ingestion services (PDF, Email, SMS), and open the dashboard in your default browser.
- **No Console:** The application runs in the background without visible command prompt windows.
- **Shutdown:** Closing the application (via System Tray or Task Manager, or by pressing Ctrl+C if run from a terminal) will cleanly shut down all background services.

## 4. Windows Startup

To make the application start automatically when you log in to Windows:

**Install Startup Shortcut:**
```powershell
AradhanaPaymentAuditor.exe --install-startup
# OR via python
python scripts/launcher.py --install-startup
```

**Remove Startup Shortcut:**
```powershell
AradhanaPaymentAuditor.exe --remove-startup
# OR via python
python scripts/launcher.py --remove-startup
```

## 5. Configuration

The launcher uses `launcher_config.json` for settings:
- `backend_port`: Port for the API (default 8000).
- `auto_open_browser`: Automatically open dashboard on launch.

## 6. Logs

Launcher and service logs can be found at:
`C:\Aradhana\PaymentAuditor\Logs\launcher.log`
