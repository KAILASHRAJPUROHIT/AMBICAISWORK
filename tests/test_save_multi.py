"""save_multi(): the RSC 2 workflow's 3-image (MAIN/ANGLE_1/ANGLE_2)
transactional capture-and-rename path.

Covers the handover spec's core file-lifecycle rules: exactly TAG.jpg/
TAG_1.jpg/TAG_2.jpg on success, no partial set ever visible mid-write,
decode-verification (not just File.exists()), and duplicate-tag protection
that never auto-renames to a sibling.
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
    return capture_tool


def _real_category(ct):
    return next(iter(ct.CATEGORY_LABELS))


def test_successful_save_produces_exactly_three_named_files(ct):
    category = _real_category(ct)
    result = ct.save_multi(
        category, _jpeg_bytes((0, 180, 255)), _jpeg_bytes((10, 190, 250)), _jpeg_bytes((20, 200, 240)),
        tag_code="TEST123", staff_name="op",
    )
    assert result["ok"] is True, result
    tray_dir = os.path.join(ct.CAPTURE_ROOT, result["folder"])

    assert result["filename"] == "TEST123.jpg"
    assert result["angle1_filename"] == "TEST123_1.jpg"
    assert result["angle2_filename"] == "TEST123_2.jpg"
    assert os.path.isfile(os.path.join(tray_dir, "TEST123.jpg"))
    assert os.path.isfile(os.path.join(tray_dir, "TEST123_1.jpg"))
    assert os.path.isfile(os.path.join(tray_dir, "TEST123_2.jpg"))

    # No temp/tag artifact files must survive (spec rules 4, 68).
    all_files = set(os.listdir(tray_dir))
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
    assert len([f for f in all_files if f.startswith("DUPTAG")]) == 3


def test_duplicate_override_replaces_existing_set(ct):
    category = _real_category(ct)
    ct.save_multi(category, _jpeg_bytes((0, 0, 0)), _jpeg_bytes((0, 0, 0)), _jpeg_bytes((0, 0, 0)),
                 tag_code="REPLACEME")
    replaced = ct.save_multi(
        category, _jpeg_bytes((255, 255, 255)), _jpeg_bytes((255, 255, 255)), _jpeg_bytes((255, 255, 255)),
        tag_code="REPLACEME", override_duplicate=True,
    )
    assert replaced["ok"] is True
    tray_dir = os.path.join(ct.CAPTURE_ROOT, replaced["folder"])
    img = cv2.imread(os.path.join(tray_dir, "REPLACEME.jpg"))
    assert img[0, 0].tolist() == [255, 255, 255]


def test_dedup_record_written_for_main_filename(ct):
    category = _real_category(ct)
    result = ct.save_multi(category, _jpeg_bytes(), _jpeg_bytes((1, 1, 1)), _jpeg_bytes((2, 2, 2)),
                           tag_code="DEDUPCHECK")
    dedup = json.loads(Path(ct.DEDUP_PATH).read_text(encoding="utf-8"))
    assert dedup["DEDUPCHECK"]["filename"] == "DEDUPCHECK.jpg"
    assert dedup["DEDUPCHECK"]["folder"] == result["folder"]
