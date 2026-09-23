"""
Tests for app._resolve_label — decides between the engine's raw parsed
label, a Gemma tag re-read, and the generic AJ-NNN fallback. Getting this
wrong means catalogue entries get filed under meaningless placeholder names
(see the "sku_unread" flag added during the reliability pass).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import app


@pytest.fixture
def two_image_mode(monkeypatch):
    """Engine-label and Gemma-tag-read resolution only apply in TWO-IMAGE mode.
    That mode is off system-wide (the archive is already tag-named), and while
    it is off the tag-derived filename is authoritative — see
    test_tag_name_is_authoritative_when_two_image_is_off below."""
    monkeypatch.setattr(app, "TWO_IMAGE_MODE_ENABLED", True)


def test_good_raw_label_used_as_is(two_image_mode):
    assert app._resolve_label("TP22/30", tag=None, pair_num=5) == "TP22/30"


def test_bad_raw_label_falls_through_to_tag_read(two_image_mode, monkeypatch, tmp_path):
    tag_path = str(tmp_path / "tag.jpg")
    open(tag_path, "wb").close()
    monkeypatch.setattr(app, "_gemma_read_tag", lambda p: "TP22/99")
    result = app._resolve_label("first line of the price tag", tag=tag_path, pair_num=5)
    assert result == "TP22/99"


def test_tag_name_is_authoritative_when_two_image_is_off():
    """Items are named once at capture time from the scanned barcode and that
    name must reach the catalogue unchanged. Engines read the number PRINTED on
    the tag, which can differ (observed: file ER22_48 vs engine ER1751), so
    with two-image mode off no engine reply may become a filename."""
    assert app.TWO_IMAGE_MODE_ENABLED is False
    assert app._resolve_label("ER1751", tag=None, pair_num=7) == "AJ-007"


def test_placeholder_phrases_rejected():
    for bad in ["price tag", "image 2", "[LABEL]", "tag in the photo"]:
        assert app._resolve_label(bad, tag=None, pair_num=1) == "AJ-001"


def test_too_short_label_rejected():
    assert app._resolve_label("A", tag=None, pair_num=2) == "AJ-002"


def test_no_raw_label_no_tag_falls_back_to_aj():
    assert app._resolve_label(None, tag=None, pair_num=7) == "AJ-007"


def test_no_raw_label_missing_tag_file_falls_back_to_aj(tmp_path):
    missing_tag = str(tmp_path / "does_not_exist.jpg")
    assert app._resolve_label(None, tag=missing_tag, pair_num=3) == "AJ-003"


def test_gemma_read_failure_falls_back_to_aj(monkeypatch, tmp_path):
    tag_path = str(tmp_path / "tag.jpg")
    open(tag_path, "wb").close()
    monkeypatch.setattr(app, "_gemma_read_tag", lambda p: "")
    assert app._resolve_label(None, tag=tag_path, pair_num=9) == "AJ-009"


def test_aj_fallback_zero_pads_pair_number():
    assert app._resolve_label(None, tag=None, pair_num=3) == "AJ-003"
    assert app._resolve_label(None, tag=None, pair_num=42) == "AJ-042"
    assert app._resolve_label(None, tag=None, pair_num=100) == "AJ-100"
