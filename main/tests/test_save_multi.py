"""save_multi(): the RSC 2 workflow's 3-image source -> one composite path.

Covers the core lifecycle rules: exactly one visible TAG.jpg on success,
three recoverable hidden originals, no partial visible output, decode-
verification, and duplicate protection that never auto-renames a sibling.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import cv2
import pytest

import capture_tool


def _jpeg_bytes(color=(0, 180, 255), size=64) -> bytes:
    """A small but real, decodable JPEG -- save_multi decode-verifies with
    cv2.imread, so placeholder text bytes won't pass."""
    img = np.full((size, size, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


@pytest.fixture
def ct(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_tool, "CAPTURE_ROOT", str(tmp_path / "capture_intake"))
    monkeypatch.setattr(capture_tool, "DEDUP_PATH", str(tmp_path / "capture_dedup.json"))
    monkeypatch.setattr(capture_tool, "TRAY_STATE_PATH", str(tmp_path / "capture_current_tray.json"))
    monkeypatch.setattr(capture_tool, "DEDUP_SETTINGS_PATH", str(tmp_path / "capture_dedup_settings.json"))
    os.makedirs(capture_tool.CAPTURE_ROOT, exist_ok=True)
    Path(capture_tool.DEDUP_PATH).write_text("{}", encoding="utf-8")
    # Quality gates are covered by their own tests elsewhere -- bypass them
    # here so this suite tests the file-lifecycle transaction, not blur/
    # visibility scoring, matching how test_capture_undo_immutable.py keeps
    # its own scope narrow.
    monkeypatch.setattr(capture_tool, "_jewellery_clearly_visible",
                        lambda b: {"ok": True, "reason": "test bypass", "unverified": True})
    # A flat-color test JPEG has ~zero Laplacian variance (no edges), which
    # would trip the real blur gate regardless of what this suite is
    # actually testing -- bypass it the same way, so corrupt-image handling
    # is tested via a genuinely undecodable byte string, not blur scoring.
    monkeypatch.setattr(capture_tool, "_blur_variance", lambda b: 999.0)
    monkeypatch.setattr(capture_tool.sam_locate, "available", lambda: False)
    return capture_tool


def _real_category(ct):
    return next(iter(ct.CATEGORY_LABELS))


def test_successful_save_produces_one_composite_and_three_hidden_sources(ct):
    category = _real_category(ct)
    result = ct.save_multi(
        category, _jpeg_bytes((0, 180, 255)), _jpeg_bytes((10, 190, 250)), _jpeg_bytes((20, 200, 240)),
        tag_code="TEST123", staff_name="op",
    )
    assert result["ok"] is True, result
    tray_dir = os.path.join(ct.CAPTURE_ROOT, result["folder"])

    assert result["filename"] == "TEST123.jpg"
    assert os.path.isfile(os.path.join(tray_dir, "TEST123.jpg"))
    assert not os.path.isfile(os.path.join(tray_dir, "TEST123_1.jpg"))
    assert not os.path.isfile(os.path.join(tray_dir, "TEST123_2.jpg"))
    assert sorted(os.listdir(result["source_archive"])) == ["angle1.jpg", "angle2.jpg", "main.jpg"]

    # No temp/tag/legacy visible artifact files survive.
    all_files = {name for name in os.listdir(tray_dir) if not name.startswith(".")}
    assert all_files == {"TEST123.jpg"}
    assert "TEST123_TAG.jpg" not in all_files
    assert "TEST123_FRONT.jpg" not in all_files
    assert "TEST123_0.jpg" not in all_files
    assert not os.path.isdir(os.path.join(tray_dir, ".staging")) or \
        not os.listdir(os.path.join(tray_dir, ".staging"))


def test_tray_count_treats_the_three_files_as_one_item(ct):
    category = _real_category(ct)
    ct.save_multi(category, _jpeg_bytes(), _jpeg_bytes((1, 1, 1)), _jpeg_bytes((2, 2, 2)),
                 tag_code="TEST200")
    summary = ct.session_summary(category)
    assert summary["captured"] == 1


def test_no_partial_set_survives_a_corrupt_angle_image(ct):
    category = _real_category(ct)
    result = ct.save_multi(
        category, _jpeg_bytes(), b"not a real jpeg at all", _jpeg_bytes((5, 5, 5)),
        tag_code="TESTBAD",
    )
    assert result["ok"] is False
    assert result["error"] == "corrupt_capture"
    # Search the whole capture root -- nothing named TESTBAD* may exist
    # anywhere, whichever tray it would have landed in.
    found = []
    for root, _dirs, files in os.walk(ct.CAPTURE_ROOT):
        found.extend(f for f in files if f.startswith("TESTBAD"))
    assert found == [], f"partial/corrupt capture leaked to disk: {found}"


def test_duplicate_tag_is_rejected_not_auto_renamed(ct):
    category = _real_category(ct)
    first = ct.save_multi(category, _jpeg_bytes(), _jpeg_bytes((1, 1, 1)), _jpeg_bytes((2, 2, 2)),
                          tag_code="DUPTAG")
    assert first["ok"] is True

    second = ct.save_multi(category, _jpeg_bytes((9, 9, 9)), _jpeg_bytes((8, 8, 8)), _jpeg_bytes((7, 7, 7)),
                           tag_code="DUPTAG")
    assert second["ok"] is False
    assert second["error"] == "duplicate"

    tray_dir = os.path.join(ct.CAPTURE_ROOT, first["folder"])
    all_files = os.listdir(tray_dir)
    assert "DUPTAG (1).jpg" not in all_files
    assert "DUPTAG_3.jpg" not in all_files
    assert len([f for f in all_files if f.startswith("DUPTAG")]) == 1


def test_duplicate_override_replaces_existing_set(ct):
    category = _real_category(ct)
    first = ct.save_multi(category, _jpeg_bytes((0, 0, 0)), _jpeg_bytes((0, 0, 0)), _jpeg_bytes((0, 0, 0)),
                          tag_code="REPLACEME")
    tray_dir = os.path.join(ct.CAPTURE_ROOT, first["folder"])
    old_bytes = Path(tray_dir, "REPLACEME.jpg").read_bytes()
    replaced = ct.save_multi(
        category, _jpeg_bytes((255, 255, 255)), _jpeg_bytes((255, 255, 255)), _jpeg_bytes((255, 255, 255)),
        tag_code="REPLACEME", override_duplicate=True,
    )
    assert replaced["ok"] is True
    assert Path(tray_dir, "REPLACEME.jpg").read_bytes() != old_bytes


def test_dedup_record_written_for_main_filename(ct):
    category = _real_category(ct)
    result = ct.save_multi(category, _jpeg_bytes(), _jpeg_bytes((1, 1, 1)), _jpeg_bytes((2, 2, 2)),
                           tag_code="DEDUPCHECK")
    dedup = json.loads(Path(ct.DEDUP_PATH).read_text(encoding="utf-8"))
    assert dedup["DEDUPCHECK"]["filename"] == "DEDUPCHECK.jpg"
    assert dedup["DEDUPCHECK"]["folder"] == result["folder"]
