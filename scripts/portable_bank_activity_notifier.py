"""Single-file Windows installer/runtime for Aradhana Bank Activity Notifier."""
import ctypes
import os
import runpy
import shutil
import subprocess
import sys
import tkinter  # Ensures the frozen executable bundles the Windows UI runtime.
import tkinter.messagebox
import tkinter.ttk


APP_NAME = "Aradhana Bank Activity Notifier"
TASK_NAME = "AradhanaBankActivityNotifier"
INSTALL_DIR = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "AradhanaBankActivityNotifier")
INSTALL_EXE = os.path.join(INSTALL_DIR, "AradhanaBankActivityNotifier.exe")


def bundled_path(relative_path):
    root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, relative_path)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate_install():
    executable = sys.executable if getattr(sys, "frozen", False) else sys.executable
    script = "" if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    arguments = '"--install"' if not script else f'"{script}" --install'
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, arguments, None, 1)
    if result <= 32:
        raise RuntimeError("Administrator approval is required to install the notifier.")


def register_task():
    action = f'New-ScheduledTaskAction -Execute "{INSTALL_EXE}" -Argument "--notifier"'
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
    if not is_admin():
        elevate_install()
        return
    os.makedirs(INSTALL_DIR, exist_ok=True)
    source = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
    if os.path.normcase(source) != os.path.normcase(INSTALL_EXE):
        shutil.copy2(source, INSTALL_EXE)
    register_task()
    subprocess.Popen([INSTALL_EXE, "--notifier"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    subprocess.Popen([INSTALL_EXE, "--configure"])


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
