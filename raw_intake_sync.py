"""
raw_intake_sync.py — keeps "master backup" as an always-current, additive
mirror of the capture tool's live intake folder.

WHY THIS EXISTS: Auto Mode needs ONE folder to read from, and the capture
tool keeps adding new trays to capture_intake continuously, so a one-time
copy would go stale within a day. This module is a background loop, started
from app.py alongside the other daemon threads, that keeps copying any file
present in capture_intake but missing from the destination — nothing more.

HISTORY: this used to also scan "FINAL CATALOGUE DND (tag-named)" (the old
manually-tagged archive) as a second source, sharing the same on-disk
convention as capture_intake. Verified 2026-07-31 by content hash that every
file in that archive was already present in raw images final, and the
archive itself is frozen (confirmed with the user — nothing new is ever
added to it), so it can never contribute anything this sync hasn't already
copied. Scanning a folder that can never produce a new file was pure wasted
work every cycle, so it was dropped as an active source. The archive folder
itself is untouched, still sitting at the path below for reference — this
module just no longer reads it.

SAFETY, hard rules:
  - Never reads/writes anything OTHER than the one named source and the one
    destination below. Never deletes or modifies a source file, ever.
  - Additive only at the destination too — a file already copied is never
    re-copied or overwritten, and nothing is ever removed from the
    destination even if the source file later disappears.
  - A source file is only copied once its mtime is at least
    _STABLE_AGE_SECS old, so a capture mid-write (jewel/tag bytes still
    being flushed to disk) can never be copied as a partial/corrupt file —
    it's simply picked up on the next cycle instead.
"""
import os
import shutil
import time
import threading

from logutil import ts

# No longer an active sync source (see module docstring) — kept only so any
# code that references this constant for historical/debugging purposes still
# finds the real path, not a NameError.
DND_SOURCE           = r"C:\Users\kaila\Desktop\FINAL CATALOGUE DND (tag-named)"
CAPTURE_INTAKE_SOURCE = r"C:\AradhanaSystems\projects\catalogue-capture\main\capture_intake"
RAW_FINAL_DIR        = r"C:\AradhanaSystems\projects\catalogue-capture\main\master backup"

_SOURCES = (CAPTURE_INTAKE_SOURCE,)
_STABLE_AGE_SECS = 10   # skip files modified more recently than this
_SYNC_INTERVAL_SECS = 60

SYNC_STATE = {
    "last_run": 0.0,
    "last_copied": 0,
    "last_error": None,
    "total_copied_lifetime": 0,
}


def _iter_source_files(source_dir):
    """Yield (abs_path, rel_path) for every file under source_dir, rel_path
    relative to source_dir itself (so it lines up 1:1 with the destination
    layout under RAW_FINAL_DIR)."""
    if not os.path.isdir(source_dir):
        return
    for root, _dirs, files in os.walk(source_dir):
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, source_dir)
            yield full, rel


def sync_once() -> int:
    """One pass over both sources. Returns the number of files copied."""
    os.makedirs(RAW_FINAL_DIR, exist_ok=True)
    now = time.time()
    copied = 0
    for source in _SOURCES:
        for src_path, rel_path in _iter_source_files(source):
            dst_path = os.path.join(RAW_FINAL_DIR, rel_path)
            if os.path.exists(dst_path):
                continue
            try:
                if now - os.path.getmtime(src_path) < _STABLE_AGE_SECS:
                    continue  # possibly still being written — try next cycle
            except OSError:
                continue
            try:
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
                copied += 1
            except OSError as e:
                print(f"[{ts()}] [raw_intake_sync] copy FAILED {src_path} -> {dst_path}: {e}")
    return copied


def sync_loop():
    """Daemon thread body — runs forever, one pass every _SYNC_INTERVAL_SECS,
    never lets a single bad pass kill the loop."""
    while True:
        try:
            copied = sync_once()
            SYNC_STATE["last_run"] = time.time()
            SYNC_STATE["last_copied"] = copied
            SYNC_STATE["last_error"] = None
            if copied:
                SYNC_STATE["total_copied_lifetime"] += copied
                print(f"[{ts()}] [raw_intake_sync] copied {copied} new file(s) into master backup")
        except Exception as e:
            SYNC_STATE["last_error"] = str(e)
            print(f"[{ts()}] [raw_intake_sync] sync pass FAILED: {e}")
        time.sleep(_SYNC_INTERVAL_SECS)
