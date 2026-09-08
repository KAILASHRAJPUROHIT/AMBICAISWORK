"""
raw_intake_sync.py: single-source mirror into master backup (renamed and
moved from "raw images final" the same day).

Changed 2026-07-31: the second source (FINAL CATALOGUE DND (tag-named)) was
dropped. Verified by content hash that every one of its 818 files already
existed in the destination, and confirmed with the user it is frozen (never
receives new files) — so it could never contribute anything this sync
hadn't already copied. These tests lock in that capture_intake is the only
source scanned, and that the additive/never-delete/stability-wait contract
is unaffected by the change.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import raw_intake_sync as ris


def test_only_capture_intake_is_an_active_source():
    assert ris._SOURCES == (ris.CAPTURE_INTAKE_SOURCE,)
    assert ris.DND_SOURCE not in ris._SOURCES


def test_sync_once_copies_from_capture_intake(tmp_path, monkeypatch):
    source = tmp_path / "capture_intake"
    dest = tmp_path / "raw_final"
    (source / "5 Earrings").mkdir(parents=True)
    old_file = source / "5 Earrings" / "ER22_1.jpg"
    old_file.write_bytes(b"jewel")
    old_time = time.time() - ris._STABLE_AGE_SECS - 5
    os.utime(old_file, (old_time, old_time))

    monkeypatch.setattr(ris, "_SOURCES", (str(source),))
    monkeypatch.setattr(ris, "RAW_FINAL_DIR", str(dest))

    copied = ris.sync_once()

    assert copied == 1
    assert (dest / "5 Earrings" / "ER22_1.jpg").read_bytes() == b"jewel"


def test_sync_once_never_touches_the_dnd_archive_path(tmp_path, monkeypatch):
    """The archive folder itself must never be read, even if it exists on
    disk at the historical DND_SOURCE path — dropping it from _SOURCES is
    what actually stops it being scanned, not just documentation."""
    source = tmp_path / "capture_intake"
    dest = tmp_path / "raw_final"
    source.mkdir()

    dnd = tmp_path / "dnd_archive"
    dnd.mkdir()
    (dnd / "should_never_be_copied.jpg").write_bytes(b"x")

    monkeypatch.setattr(ris, "_SOURCES", (str(source),))
    monkeypatch.setattr(ris, "DND_SOURCE", str(dnd))
    monkeypatch.setattr(ris, "RAW_FINAL_DIR", str(dest))

    ris.sync_once()

    assert not (dest / "should_never_be_copied.jpg").exists()


def test_sync_once_skips_files_still_being_written(tmp_path, monkeypatch):
    source = tmp_path / "capture_intake"
    dest = tmp_path / "raw_final"
    source.mkdir()
    fresh = source / "ER22_2.jpg"
    fresh.write_bytes(b"jewel")  # mtime = now, well within _STABLE_AGE_SECS

    monkeypatch.setattr(ris, "_SOURCES", (str(source),))
    monkeypatch.setattr(ris, "RAW_FINAL_DIR", str(dest))

    copied = ris.sync_once()

    assert copied == 0
    assert not (dest / "ER22_2.jpg").exists()


def test_sync_once_never_recopies_or_overwrites(tmp_path, monkeypatch):
    source = tmp_path / "capture_intake"
    dest = tmp_path / "raw_final"
    source.mkdir()
    src_file = source / "ER22_3.jpg"
    src_file.write_bytes(b"original")
    old_time = time.time() - ris._STABLE_AGE_SECS - 5
    os.utime(src_file, (old_time, old_time))
    dest.mkdir()
    dst_file = dest / "ER22_3.jpg"
    dst_file.write_bytes(b"already-copied-earlier")

    monkeypatch.setattr(ris, "_SOURCES", (str(source),))
    monkeypatch.setattr(ris, "RAW_FINAL_DIR", str(dest))

    copied = ris.sync_once()

    assert copied == 0
    assert dst_file.read_bytes() == b"already-copied-earlier"
