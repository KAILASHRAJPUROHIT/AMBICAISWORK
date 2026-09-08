"""Single-file Windows installer/runtime for Aradhana Bank Activity Notifier."""
import ctypes  # Bundled notifier uses this for active-monitor placement.
import json  # Dynamic bundled scripts import this at runtime.
import os
import runpy
import shutil
import subprocess
import sys
import tkinter  # Ensures the frozen executable bundles the Windows UI runtime.
import tkinter.messagebox
import tkinter.ttk
from datetime import datetime, timedelta, timezone  # Bundled notifier/config imports.
from urllib.request import urlopen  # Bundled notifier imports.


APP_NAME = "Aradhana Bank Activity Notifier"
TASK_NAME = "AradhanaBankActivityNotifierUser"
INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "AradhanaBankActivityNotifier", "releases")
# Bump only through scripts/build_bank_activity_notifier_release.ps1.  Every
# running notifier compares this value to the LAN checksum release manifest.
APP_VERSION = "1.7.0"


def bundled_path(relative_path):
    root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, relative_path)


def register_task(installed_exe):
    escaped_exe = installed_exe.replace("'", "''")
    action = f"New-ScheduledTaskAction -Execute '{escaped_exe}' -Argument '--notifier'"
    command = (
        "$ErrorActionPreference='Stop'; "
        f"$action={action}; "
        "$trigger=New-ScheduledTaskTrigger -AtLogOn; "
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger $trigger "
        "-Description 'Aradhana native bank transaction popups.' -Force | Out-Null; "
        f"Enable-ScheduledTask -TaskName '{TASK_NAME}' | Out-Null"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        text=True, capture_output=True, check=False,
    )
    if result.returncode == 0:
        return "scheduled-task"

    # Some managed PCs prohibit per-user task creation. HKCU Run is scoped to
    # the current Windows account and needs no administrator access.
    run_value = f'"{installed_exe}" --notifier'
    fallback = subprocess.run(
        ["reg.exe", "add", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "/v", TASK_NAME,
         "/t", "REG_SZ", "/d", run_value, "/f"],
        text=True, capture_output=True, check=False,
    )
    if fallback.returncode != 0:
        detail = (result.stderr or result.stdout or fallback.stderr or fallback.stdout).strip()
        raise RuntimeError(f"Could not register startup: {detail}")
    return "login-startup"


def retire_legacy_notifiers():
    """Leave exactly one notifier runtime after upgrades or repeat installs."""
    current_pid = os.getpid()
    command = (
        "Get-CimInstance Win32_Process -Filter \"name = 'pythonw.exe'\" | "
        "Where-Object { $_.CommandLine -like '*bank_activity_notifier.py*' } | "
        f"Where-Object {{ $_.ProcessId -ne {current_pid} }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; "
        "Get-CimInstance Win32_Process -Filter \"name = 'AradhanaBankActivityNotifier.exe'\" | "
        f"Where-Object {{ $_.ProcessId -ne {current_pid} }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; "
        "Unregister-ScheduledTask -TaskName 'AradhanaBankActivityNotifier' -Confirm:$false -ErrorAction SilentlyContinue"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], check=False)


def install(configure=True):
    retire_legacy_notifiers()
    release_dir = os.path.join(INSTALL_DIR, f"release-{APP_VERSION}")
    os.makedirs(release_dir, exist_ok=True)
    installed_exe = os.path.join(release_dir, "AradhanaBankActivityNotifier.exe")
    source = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
    shutil.copy2(source, installed_exe)
    startup_mode = register_task(installed_exe)
    subprocess.Popen([installed_exe, "--notifier"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if configure:
        subprocess.Popen([installed_exe, "--configure"])
    return startup_mode


def run_bundled(script_name):
    os.environ["BANK_NOTIFIER_VERSION"] = APP_VERSION
    os.environ["BANK_NOTIFIER_EXECUTABLE"] = os.path.abspath(sys.executable)
    runpy.run_path(bundled_path(os.path.join("scripts", script_name)), run_name="__main__")


def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "--install"
    if mode == "--notifier":
        run_bundled("bank_activity_notifier.py")
    elif mode == "--configure":
        run_bundled("configure_bank_activity_notifier.py")
    elif mode == "--install":
        install()
    elif mode == "--update":
        install(configure=False)
    else:
        raise SystemExit(f"Unknown mode: {mode}")


if __name__ == "__main__":
    main()
