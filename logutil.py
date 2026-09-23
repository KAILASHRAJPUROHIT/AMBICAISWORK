"""
Shared timestamp helper for the engine status-print helpers (_st()) scattered
across app.py/copilot_img.py/codex_img.py/etc.

Every print() in this codebase used to go to a hidden window's stdout with
nothing capturing it — now redirected into run.log by launch_tool.vbs, but
still just a wall of unlabelled text. A print()-per-line log with no
timestamp is nearly useless for the actual thing it's needed for: figuring
out what happened overnight when nobody was watching. This adds a
consistent "[HH:MM:SS]" prefix so entries can be correlated across engines
and located by time when reviewing run.log the next morning.
"""
import time


def ts() -> str:
    return time.strftime("%H:%M:%S")
