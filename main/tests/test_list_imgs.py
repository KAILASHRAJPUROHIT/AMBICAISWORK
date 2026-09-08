"""
Tests for app._list_imgs — the dedup-by-basename logic flagged in the
reliability audit as a real (if rare) risk: two genuinely different files
sharing a basename (IMG_5316.jpg vs IMG_5316.JPEG from a different export
pass) silently drop one with no way to know which.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app


def _touch(folder, name):
    open(os.path.join(folder, name), "wb").close()


def test_dedups_same_basename_different_extension(tmp_path):
    _touch(tmp_path, "IMG_1.jpg")
    _touch(tmp_path, "IMG_1.jpeg")
    _touch(tmp_path, "IMG_2.jpg")
    result = app._list_imgs(str(tmp_path))
    basenames = sorted(os.path.splitext(os.path.basename(f))[0].lower() for f in result)
    # Only one of IMG_1.jpg / IMG_1.jpeg survives — this test documents the
    # existing (imperfect but understood) behavior rather than asserting it's ideal.
    assert basenames == ["img_1", "img_2"]


def test_preserves_camera_shot_order(tmp_path):
    _touch(tmp_path, "IMG_3.jpg")
    _touch(tmp_path, "IMG_1.jpg")
    _touch(tmp_path, "IMG_2.jpg")
    result = app._list_imgs(str(tmp_path))
    names = [os.path.basename(f) for f in result]
    assert names == ["IMG_1.jpg", "IMG_2.jpg", "IMG_3.jpg"]


def test_empty_folder_returns_empty_list(tmp_path):
    assert app._list_imgs(str(tmp_path)) == []
