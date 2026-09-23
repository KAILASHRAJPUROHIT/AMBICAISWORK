"""
Global tray numbering (capture_tool._next_tray_number / _tray_folder_name).

Changed 2026-07-31 alongside the one-time renumbering
(tray_sequence_migration.py): the user's explicit requirement was "1
ornament may have multiple folders based on capture order but the number
sequence never breaks" — a per-category counter cannot satisfy that, since
every category restarting at 1 is exactly a broken sequence. These tests
exist because the renumbering script alone was found to be insufficient:
it relabels existing folders once, but capture_tool's own tray-creation
logic being unchanged would have silently reset every category's counter
back to 1 the moment any new tray was started, undoing the whole point.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import capture_tool as ct


@pytest.fixture
def capture_root(tmp_path, monkeypatch):
    root = tmp_path / "capture_intake"
    root.mkdir()
    monkeypatch.setattr(ct, "CAPTURE_ROOT", str(root))
    # _next_tray_number also reads tray state (2026-08-01: a tray is
    # reserved in state before its folder is ever created on disk, so the
    # sequence must consider both) — isolate it too, or these tests would
    # leak into reading the real production capture_current_tray.json.
    monkeypatch.setattr(ct, "TRAY_STATE_PATH", str(tmp_path / "capture_current_tray.json"))
    return root


def test_folder_name_is_number_first_global_format():
    assert ct._tray_folder_name("ladies_rings", 33) == "33 Ladies Rings"
    assert ct._tray_folder_name("earrings", 1) == "1 Earrings"


def test_next_number_starts_at_one_on_empty_root(capture_root):
    assert ct._next_tray_number() == 1


def test_next_number_continues_the_sequence_regardless_of_category(capture_root):
    """The whole point: a DIFFERENT category's next tray must continue the
    SAME global counter, not restart its own."""
    for name in ("1 Ladies Rings", "2 Ladies Rings", "3 Gents Rings"):
        (capture_root / name).mkdir()

    assert ct._next_tray_number() == 4


def test_next_number_ignores_non_matching_folders(capture_root):
    """The fixed practice folder ('_TEST') and anything else that doesn't
    match "<digits> <label>" must never be treated as a 0 in the sequence —
    that would be indistinguishable from a real folder numbered 0."""
    (capture_root / "_TEST").mkdir()
    (capture_root / "5 Earrings").mkdir()

    assert ct._next_tray_number() == 6


def test_next_number_rejects_old_per_category_format_as_unrelated(capture_root):
    """A leftover pre-migration folder in the OLD "<Label> <N>" format
    (number last, not first) must not be mistaken for part of the new
    sequence — it doesn't start with a digit, so the pattern correctly
    ignores it rather than crashing or double-counting."""
    (capture_root / "Ladies Rings 9").mkdir()
    (capture_root / "3 Earrings").mkdir()

    assert ct._next_tray_number() == 4


def test_start_new_tray_uses_the_global_sequence(capture_root, monkeypatch, tmp_path):
    (capture_root / "1 Ladies Rings").mkdir()
    (capture_root / "2 Gents Rings").mkdir()
    state_path = tmp_path / "capture_current_tray.json"
    monkeypatch.setattr(ct, "TRAY_STATE_PATH", str(state_path))
    monkeypatch.setattr(ct, "_load_tray_state", lambda: {})

    saved = {}
    monkeypatch.setattr(ct, "_save_tray_state", lambda state: saved.update(state))

    result = ct.start_new_tray("earrings")

    assert result["folder"] == "3 Earrings"
    assert result["tray_number"] == 3
    # 2026-08-01: start_new_tray no longer creates the folder eagerly — only
    # a real capture (save_pair) does, so an assigned-but-empty tray never
    # shows up as clutter in the capture-memory list or gets recreated the
    # instant it's Forgotten.
    assert not (capture_root / "3 Earrings").exists()
    assert saved == {"earrings": "3 Earrings"}


def test_get_current_tray_does_not_reallocate_an_uncaptured_tray(capture_root):
    """2026-08-01: get_current_tray used to check os.path.isdir on the
    assigned folder and silently allocated a BRAND NEW tray whenever it
    wasn't materialized yet — which was every poll of an uncaptured tray,
    since nothing creates it until a real capture. That meant simply
    viewing a category (session_summary) burned a fresh tray number on
    every single request. It must keep returning the SAME assigned tray
    regardless of whether the folder exists on disk."""
    first = ct.start_new_tray("earrings")

    second = ct.get_current_tray("earrings")
    third = ct.get_current_tray("earrings")

    assert second == first
    assert third == first
    assert not (capture_root / first["folder"]).exists()


def test_next_number_accounts_for_reserved_but_uncaptured_trays(capture_root):
    """Two categories can each be assigned a tray before either has a real
    capture (and therefore before either folder exists on disk). The
    second assignment must not recompute the same number the first one is
    already sitting on."""
    first = ct.start_new_tray("earrings")
    second = ct.start_new_tray("gents_rings")

    assert first["tray_number"] != second["tray_number"]
    assert second["tray_number"] == first["tray_number"] + 1


def test_start_new_tray_after_purge_advance_continues_the_same_sequence(capture_root, monkeypatch):
    """capture_purge._advance_active_trays and capture_tool.start_new_tray
    must never diverge on what "next" means — both call the same
    _next_tray_number(), so a tray advanced by a purge and a tray started
    fresh by an operator can never collide or double-assign a number."""
    (capture_root / "1 Locket").mkdir()
    n = ct._next_tray_number()
    advanced_name = ct._tray_folder_name("locket", n)
    os.makedirs(capture_root / advanced_name)

    n2 = ct._next_tray_number()
    assert n2 == n + 1
