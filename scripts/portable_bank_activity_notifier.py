"""Single-file Windows installer/runtime for Aradhana Bank Activity Notifier."""
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


def bundled_path(relative_path):
    root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, relative_path)


def register_task(installed_exe):
    action = f'New-ScheduledTaskAction -Execute "{installed_exe}" -Argument "--notifier"'
    command = (
        "$ErrorActionPreference='Stop'; "
        f"$action={action}; "
        "$trigger=New-ScheduledTaskTrigger -AtLogOn; "
        "$principal=New-ScheduledTaskPrincipal -UserId \"$env:USERDOMAIN\\$env:USERNAME\" -LogonType Interactive -RunLevel Limited; "
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger $trigger -Principal $principal "
        "-Description 'Aradhana native bank transaction popups.' -Force | Out-Null"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], check=True)


def install():
    release_dir = os.path.join(INSTALL_DIR, f"release-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    os.makedirs(release_dir, exist_ok=True)
    installed_exe = os.path.join(release_dir, "AradhanaBankActivityNotifier.exe")
    source = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
    shutil.copy2(source, installed_exe)
    register_task(installed_exe)
    subprocess.Popen([installed_exe, "--notifier"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    subprocess.Popen([installed_exe, "--configure"])


def run_bundled(script_name):
    runpy.run_path(bundled_path(os.path.join("scripts", script_name)), run_name="__main__")


def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "--install"
    if mode == "--notifier":
        run_bundled("bank_activity_notifier.py")
    elif mode == "--configure":
        run_bundled("configure_bank_activity_notifier.py")
    elif mode == "--install":
        install()
    else:
        raise SystemExit(f"Unknown mode: {mode}")


if __name__ == "__main__":
    main()
