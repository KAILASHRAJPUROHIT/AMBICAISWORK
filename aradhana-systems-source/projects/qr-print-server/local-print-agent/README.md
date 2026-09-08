# Aradhana Local Print Agent

This is the background daemon that runs on the Windows machine connected to the HP Laser MFP 330. It securely polls the cloud server, downloads jobs, mathematically generates the ID card layout (if requested), and pushes the final file to the spooler via SumatraPDF.

## Features Included
*   **Idempotent Execution**: SQLite integration prevents double-printing.
*   **Auto Duplexing**: Automatically detects 2-page PDFs and appends `,duplex` to the hardware command.
*   **Multi-Copy Engine**: Supports 1-5 copies securely via native `-print-settings`.
*   **ID Card Math**: Handles up to 6 slots per A4, intelligently stacking front/back pairings in single slots.

## Installation

1.  **Install Python Dependencies**:
    Open an Administrator terminal in this directory and run:
    ```cmd
    pip install -r requirements.txt
    ```

2.  **Configure Environment**:
    Create or edit the `.env` file to match your absolute paths and printer name:
    ```env
    CLOUD_SERVER_URL=https://print.aradhana.com
    AGENT_TOKEN=aradhana_secret_agent_token_2026
    PRINTER_NAME=HPF8EDFC0532A7(HP Laser MFP 330)
    SUMATRA_PATH=C:\Users\kaila\AppData\Local\SumatraPDF\SumatraPDF.exe
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
*   **`.env` Missing**: The agent will crash immediately if the `.env` file is missing. Ensure the file is created in the `local-print-agent` directory and then run `restart_agent.bat`.
*   **Python Path Wrong**: If the installer fails, verify that Python is actually installed at `C:\Users\kaila\AppData\Local\Programs\Python\Python311\pythonw.exe`. If it is installed elsewhere, you must edit the `.bat` scripts to match your system.
*   **Agent Not Polling**: Run `check_status.bat`. If `pythonw.exe` is not in the running processes list, it crashed. Check the recent log activity printed by the script or open `logs/agent.log` for the exact Python error.
*   **Render Server Sleeping**: If your cloud backend is hosted on a free tier (like Render), it will go to sleep after 15 minutes of inactivity. The first upload of the morning might take ~50 seconds to wake the server up before the queue ID appears.
*   **No Print After Upload**: If the upload succeeds but nothing prints, verify that your `AGENT_TOKEN` in the `.env` exactly matches the backend. Also, verify that your `SUMATRA_PATH` is correct and SumatraPDF is installed.