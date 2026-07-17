# AMBIC SmartQR — Local Print Agent

This is the background daemon that runs on the Windows machine connected to your printer. It securely polls the cloud server for **your business's own** print jobs, downloads them, generates the ID card layout (if requested), and pushes the final file to the spooler via SumatraPDF.

## Features Included
*   **Tenant-scoped polling**: Authenticates with `TENANT_SLUG` + `AGENT_API_KEY`, so this agent only ever sees jobs belonging to your business — never another shop's.
*   **Idempotent Execution**: SQLite integration prevents double-printing.
*   **Auto Duplexing**: Automatically detects 2-page PDFs and appends `,duplex` to the hardware command.
*   **Multi-Copy Engine**: Supports multiple copies via native `-print-settings`.
*   **ID Card Math**: Handles multiple slots per A4, intelligently stacking front/back pairings in single slots.

## Installation

1.  **Install Python Dependencies**:
    Open an Administrator terminal in this directory and run:
    ```cmd
    pip install -r requirements.txt
    ```

2.  **Configure Environment**:
    Copy `.env.example` to `.env` and fill in your values. Get `TENANT_SLUG` and
    `AGENT_API_KEY` from your business's `/setup` page on the cloud server:
    ```env
    CLOUD_SERVER_URL=https://your-ambic-smartqr-server.example.com
    PRINTER_NAME=Your Printer Name
    SUMATRA_PATH=C:\Path\To\SumatraPDF.exe
    TENANT_SLUG=your-business-slug
    AGENT_API_KEY=paste-from-setup-page
    ```

## Automated Background Setup (Windows Task Scheduler)

We use native Windows Task Scheduler to ensure the print agent starts silently whenever the computer is turned on, running in the background before anyone even logs in.

*No manual setup is required. Use the provided batch scripts:*

1. **Install & Start**: Right-click `install_autostart.bat` -> **Run as Administrator**.
2. **Check Status**: Double-click `check_status.bat` to see if the agent is polling and view the latest logs.
3. **Restart Agent**: Right-click `restart_agent.bat` -> **Run as Administrator** (Use this if you edited the `.env` file and need the agent to pick up the changes).
4. **Uninstall**: Right-click `uninstall_autostart.bat` -> **Run as Administrator**.

## Troubleshooting

If prints are not firing automatically, consult this list:

*   **Printer Offline**: Check physical USB/Network cables. Ensure `PRINTER_NAME` in your `.env` exactly matches the spelling found in Windows *Printers & Scanners* settings.
*   **`.env` Missing**: The agent will refuse to start if the `.env` file is missing required values. Copy `.env.example` to `.env`, fill it in, then run `restart_agent.bat`.
*   **Python Path Wrong**: If the installer fails, verify Python is actually installed where the `.bat` scripts expect. If it's installed elsewhere, edit the scripts to match your system.
*   **Agent Not Polling**: Run `check_status.bat`. If `pythonw.exe` is not in the running processes list, it crashed. Check the recent log activity printed by the script or open `logs/agent.log` for the exact Python error.
*   **Server Sleeping**: If your cloud backend is hosted on a free tier that sleeps after inactivity, the first upload of the day might take longer to wake the server up before the queue ID appears.
*   **401 "Invalid or missing agent key"**: `AGENT_API_KEY` in `.env` doesn't match the one stored for `TENANT_SLUG` — re-copy both from that business's `/setup` page.
*   **No Print After Upload**: If the upload succeeds but nothing prints, verify `SUMATRA_PATH` is correct and SumatraPDF is installed.
