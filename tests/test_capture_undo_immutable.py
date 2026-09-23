"""Undo preserves raw capture history and permits a deliberate recapture."""

import json
import os
import sys
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import capture_tool
import capture_voids


def _configure_capture(tmp_path, monkeypatch):
    capture_root = tmp_path / "capture_intake"
    tray = capture_root / "Earrings 1"
    archive = tray / capture_tool.TAG_ARCHIVE_DIRNAME
    archive.mkdir(parents=True)
    primary = tray / "ER22_1.jpg"
    tag = archive / "ER22_1_tag.jpg"
    primary.write_bytes(b"original jewellery bytes")
    tag.write_bytes(b"original tag bytes")

    dedup_path = tmp_path / "capture_dedup.json"
    tray_state_path = tmp_path / "capture_current_tray.json"
    void_path = tmp_path / "capture_voids.json"
    settings_path = tmp_path / "capture_dedup_settings.json"
    dedup_path.write_text(
        json.dumps(
            {
                "ER22/1": {
                    "folder": "Earrings 1",
                    "filename": "ER22_1.jpg",
                    "category": "earrings",
                    "staff": "test",
                    "ts": 100.0,
                }
            }
        ),
        encoding="utf-8",
    )
    tray_state_path.write_text(
        json.dumps({"earrings": "Earrings 1"}), encoding="utf-8"
    )

    monkeypatch.setattr(capture_tool, "CAPTURE_ROOT", str(capture_root))
    monkeypatch.setattr(capture_tool, "DEDUP_PATH", str(dedup_path))
    monkeypatch.setattr(capture_tool, "TRAY_STATE_PATH", str(tray_state_path))
    monkeypatch.setattr(capture_tool, "VOID_REGISTRY_PATH", str(void_path))
    monkeypatch.setattr(capture_tool, "DEDUP_SETTINGS_PATH", str(settings_path))
    return primary, tag, dedup_path, void_path


def test_undo_tombstones_pair_without_deleting_bytes_and_allows_recapture(
    tmp_path, monkeypatch
):
    primary, tag, dedup_path, void_path = _configure_capture(tmp_path, monkeypatch)
    before = {
        primary: (primary.read_bytes(), primary.stat().st_mtime_ns),
        tag: (tag.read_bytes(), tag.stat().st_mtime_ns),
    }

    result = capture_tool.undo_last("earrings")

    assert result == {
        "ok": True,
        "action": "voided",
        "voided": True,
        "removed_code": "ER22/1",
        "voided_primary_path": "Earrings 1/ER22_1.jpg",
        "voided_tag_path": "Earrings 1/_tag_archive/ER22_1_tag.jpg",
        "preserved": True,
        "preserved_files": 1,
        "preserved_bytes": len(b"original jewellery bytes"),
        "dedup_removed": True,
    }
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (primary, tag)
    } == before
    assert json.loads(dedup_path.read_text(encoding="utf-8")) == {}
    tombstones = capture_voids.load_void_registry(void_path)
    assert tombstones["Earrings 1/ER22_1.jpg"]["tag_path"] == (
        "Earrings 1/_tag_archive/ER22_1_tag.jpg"
    )
    assert capture_tool.check_duplicate("ER22/1") is None

    recaptured = capture_tool.save_pair(
        "earrings",
        b"new jewellery bytes",
        b"new tag bytes",
        "ER22/1",
        staff_name="test",
        override_blur=True,
    )
    assert recaptured["ok"] is True
    assert recaptured["filename"] == "ER22_1_2.jpg"
    assert primary.read_bytes() == b"original jewellery bytes"
    assert tag.read_bytes() == b"original tag bytes"
    assert primary.with_name("ER22_1_2.jpg").read_bytes() == b"new jewellery bytes"
    assert not tag.with_name("ER22_1_2_tag.jpg").exists()


def test_missing_legacy_tag_archive_does_not_block_undo(
    tmp_path, monkeypatch
):
    primary, tag, dedup_path, void_path = _configure_capture(tmp_path, monkeypatch)
    tag.unlink()
    result = capture_tool.undo_last("earrings")

    assert result["ok"] is True
    assert result["preserved_files"] == 1
    assert primary.read_bytes() == b"original jewellery bytes"
    assert json.loads(dedup_path.read_text(encoding="utf-8")) == {}
    assert capture_voids.is_voided("Earrings 1/ER22_1.jpg", void_path)


def test_retry_reuses_tombstone_after_dedup_write_interruption(
    tmp_path, monkeypatch
):
    primary, tag, dedup_path, void_path = _configure_capture(tmp_path, monkeypatch)
    original_write = capture_tool._atomic_write_json
    failed_once = False

    def fail_first_dedup_write(path, data):
        nonlocal failed_once
        if path == str(dedup_path) and not failed_once:
            failed_once = True
            raise OSError("simulated dedup interruption")
        return original_write(path, data)

    monkeypatch.setattr(capture_tool, "_atomic_write_json", fail_first_dedup_write)

    try:
        capture_tool.undo_last("earrings")
    except OSError as exc:
        assert "simulated dedup interruption" in str(exc)
    else:
        raise AssertionError("the simulated dedup interruption was not raised")

    assert primary.read_bytes() == b"original jewellery bytes"
    assert tag.read_bytes() == b"original tag bytes"
    assert capture_voids.is_voided("Earrings 1/ER22_1.jpg", void_path)
    assert capture_tool.check_duplicate("ER22/1") is None

    recovered = capture_tool.undo_last("earrings")
    assert recovered["ok"] is True
    assert recovered["voided"] is True
    assert json.loads(dedup_path.read_text(encoding="utf-8")) == {}
    assert len(capture_voids.load_void_registry(void_path)) == 1
