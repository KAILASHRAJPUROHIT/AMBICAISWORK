# Aradhana Print Agent Installation Guide

This guide provides instructions for installing and setting up the Aradhana Print Agent on a Windows PC/Server.

## Prerequisites

Before you begin, ensure you have the following:

1.  **Windows Operating System:** The agent is designed for Windows.
2.  **Internet Connection:** Required for initial setup to download Python and its dependencies (if not using the offline wheelhouse).
3.  **Administrator Privileges:** Necessary for creating the installation directory, scheduled tasks, and installing Python dependencies.
4.  **Printer:** A default printer connected and configured on the system.
5.  **SumatraPDF:** A lightweight PDF reader (recommended for best performance). If not detected, the installer will prompt you for its location.

## Installation Steps

1.  **Extract the Package:**
    *   Download the `install_aradhana_print_agent.zip` package.
    *   Extract its contents to a temporary location (e.g., `C:	emp\AradhanaPrintAgentInstaller`).

2.  **Run the Installer:**
    *   Navigate to the extracted folder.
    *   **Right-click** on `install_aradhana_print_agent.bat` and select "**Run as administrator**".
    *   Follow the prompts in the command window:
        *   **Pythonw.exe Path:** If `pythonw.exe` is not found, you will be asked to provide the full path to your Python installation's `pythonw.exe` (e.g., `C:\Python39\pythonw.exe`).
        *   **Default Printer Name:** Enter the exact name of your default printer. (See "How to Find Your Printer Name" below).
        *   **SumatraPDF.exe Path:** If SumatraPDF is not detected, you will be asked to provide its full path (e.g., `C:\Program Files\SumatraPDF\SumatraPDF.exe`).

3.  **Completion:**
    *   The installer will set up the agent in `C:\AradhanaPrintAgent`, install necessary Python dependencies, create required folders, and configure a Windows Scheduled Task to run the agent automatically on system startup.
    *   The agent will start immediately after installation.

## Printer Setup

The Aradhana Print Agent relies on a correctly configured default printer.

### How to Find Your Printer Name

1.  Open **Command Prompt** or **PowerShell**.
2.  Type the following command and press Enter:
    ```bash
    wmic printer get name
    ```
3.  Look for the exact name of the printer you wish to use (e.g., "EPSON L3110 Series"). Copy this name precisely when prompted by the installer.

## Troubleshooting

*   **"Error: Could not create C:\AradhanaPrintAgent. Please run as administrator."**: Rerun `install_aradhana_print_agent.bat` by right-clicking and selecting "Run as administrator."
*   **"Error: Pythonw.exe not found..."**: Ensure Python is installed and provide the correct path when prompted. If Python is not installed, please install Python (version 3.7+) from python.org.
*   **"Error: Failed to install Python dependencies."**: Check your internet connection or verify the `wheelhouse` folder is present and contains the necessary `.whl` files.
*   **"Warning: Printer '...' not found."**: The agent might not be able to send print jobs. Verify the printer name in `C:\AradhanaPrintAgent\.env` and ensure the printer is installed and online.
*   **"Warning: SumatraPDF not found..."**: The agent uses SumatraPDF for printing. Ensure it's installed and the path in `C:\AradhanaPrintAgent\.env` is correct. If SumatraPDF is not installed, please install it or the agent will not be able to print PDFs.
*   **Agent Not Printing**:
    1.  Check the agent's status using `check_status.bat`.
    2.  Review the logs (see "How to Check Logs" below).
    3.  Restart the agent using `restart_agent.bat`.

### How to Test the Agent

You can manually run the agent for testing purposes from its installation directory:

1.  Open **Command Prompt** or **PowerShell**.
2.  Navigate to the installation directory:
    ```bash
    cd C:\AradhanaPrintAgent
    ```
3.  Run the agent:
    ```bash
    python agent.py
    ```
    (Note: This will run with a console window visible. The scheduled task runs it hidden with `pythonw.exe`.)

### How to Check Logs

Agent logs are stored in `C:\AradhanaPrintAgent\logs\agent.log`.

1.  Open `C:\AradhanaPrintAgent\logs\agent.log` with a text editor to view detailed activity and error messages.
2.  Use `check_status.bat` (located in `C:\AradhanaPrintAgent`) to quickly view the last 30 lines of the log.

## Helper Scripts (in `C:\AradhanaPrintAgent`)

*   `check_status.bat`: Checks if the scheduled task exists, if the agent process is running, and shows the last 30 lines of the log file.
*   `restart_agent.bat`: Stops any running agent processes, then stops and restarts the scheduled task.
*   `uninstall_autostart.bat`: Stops and deletes the scheduled task. It will ask for confirmation before deleting the `C:\AradhanaPrintAgent` folder.
