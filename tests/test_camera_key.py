"""
Pairing/sort-order tests for app._camera_key.

This drives the whole "which photo is the jewel, which is the tag" pairing
logic (odd position = jewel, even = tag) — a bug here silently mispairs
every subsequent step, so it's worth locking down with real assertions.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app


def test_sorts_by_last_number_in_filename():
    files = ["IMG_5316.jpg", "IMG_5317.jpg", "IMG_5300.jpg"]
    files.sort(key=app._camera_key)
    assert files == ["IMG_5300.jpg", "IMG_5316.jpg", "IMG_5317.jpg"]


def test_uses_rightmost_number_not_leftmost():
    # A filename with two numeric runs — the shot counter is the LAST one,
    # not the first (e.g. a date-prefixed camera filename).
    files = ["20240626_120099.jpg", "20240626_120001.jpg"]
    files.sort(key=app._camera_key)
    assert files == ["20240626_120001.jpg", "20240626_120099.jpg"]


def test_no_number_sorts_by_name():
    files = ["zeta.jpg", "alpha.jpg"]
    files.sort(key=app._camera_key)
    assert files == ["alpha.jpg", "zeta.jpg"]


def test_case_insensitive():
    files = ["IMG_2.JPG", "img_1.jpg"]
    files.sort(key=app._camera_key)
    assert files == ["img_1.jpg", "IMG_2.JPG"]


def test_full_path_input():
    # _camera_key is fed full paths (glob.glob results), not bare filenames.
    files = [r"C:\input\IMG_20.jpg", r"C:\input\IMG_5.jpg"]
    files.sort(key=app._camera_key)
    assert files == [r"C:\input\IMG_5.jpg", r"C:\input\IMG_20.jpg"]
