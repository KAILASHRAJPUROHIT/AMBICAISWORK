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
    Edit the `.env` file to match your absolute paths and printer name:
    ```env
    CLOUD_SERVER_URL=https://print.aradhana.com
    PRINTER_NAME=HPF8EDFC0532A7(HP Laser MFP 330)
    SUMATRA_PATH=C:\Users\kaila\AppData\Local\SumatraPDF\SumatraPDF.exe
    ```

## Running as a Hidden Background Service (Windows Task Scheduler)

To ensure this agent runs automatically when the PC turns on (without showing a black console window to the cashier), we will use `pythonw.exe`:

1.  Open **Task Scheduler** (`taskschd.msc` from the Start Menu).
2.  Click **Create Basic Task** on the right.
3.  Name: `Aradhana Print Agent`
4.  Trigger: **When the computer starts**
5.  Action: **Start a program**
6.  Program/script: Browse and select `pythonw.exe` (usually in `C:\Python3X\pythonw.exe` or your virtual environment).
7.  Add arguments: `agent.py`
8.  Start in: `C:\aradhana_qr_print_server_v3\local-print-agent` (Important! This ensures `.env` and `agent.log` save correctly).
9.  Click **Finish**.

Now, the agent will poll every 5 seconds silently in the background.

## Troubleshooting

If prints are not firing:
1.  Check `logs/agent.log` for Python errors or timeouts.
2.  Ensure `SumatraPDF` is installed in the exact directory specified in `.env`.
3.  Ensure the `PRINTER_NAME` exactly matches the spelling in your Windows Control Panel (Printers & Scanners).