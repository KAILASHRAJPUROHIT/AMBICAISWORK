"""
single_instance.py -- enforce that only one process of a given name is ever
serving on this machine at a time.

WHY THIS EXISTS: this session repeatedly lost time to stale/duplicate
processes -- NSSM's own reported PID going stale after a restart, a manual
test run left sitting alongside the real service, a stray full-suite pytest
run idling against a live Chrome session. Every time, resolving it meant
manually cross-referencing netstat's actually-listening PID against
Win32_Process creation timestamps. This makes "exactly one instance stays
running" a property the process enforces on itself at startup, instead of
something a human has to verify by hand every time.

Call enforce_single_instance(name) once, early, before binding any port.
If a previous process recorded under that name is still alive, it is
killed outright -- the newest instance always wins. Not just a lock that
refuses to start: the whole point is that restarting always leaves exactly
one process live, matching how NSSM's Stop-then-Start is meant to behave.
"""
import atexit
import os

import psutil

BASE = os.path.dirname(os.path.abspath(__file__))
LOCK_DIR = os.path.join(BASE, "_instance_locks")


def _lock_path(name: str) -> str:
    return os.path.join(LOCK_DIR, f"{name}.pid")


def enforce_single_instance(name: str, timeout: float = 5.0) -> None:
    os.makedirs(LOCK_DIR, exist_ok=True)
    path = _lock_path(name)
    my_pid = os.getpid()

    if os.path.isfile(path):
        try:
            old_pid = int(open(path).read().strip())
        except (ValueError, OSError):
            old_pid = None
        if old_pid and old_pid != my_pid and psutil.pid_exists(old_pid):
            try:
                proc = psutil.Process(old_pid)
                cmdline = " ".join(proc.cmdline()).lower()
                # Guard against a recycled PID belonging to an unrelated
                # process (the OS can reuse a PID number after the real
                # prior instance already exited): only kill it if its own
                # command line still names this same script.
                if name.lower() in cmdline:
                    proc.terminate()
                    try:
                        proc.wait(timeout=timeout)
                    except psutil.TimeoutExpired:
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    with open(path, "w") as f:
        f.write(str(my_pid))

    def _release():
        try:
            if os.path.isfile(path) and int(open(path).read().strip()) == my_pid:
                os.remove(path)
        except (OSError, ValueError):
            pass

    atexit.register(_release)
