"""
Capture-memory (dedup) admin: master switch + per-folder forgetting.

These exist because the "already captured" block is correct almost always and
intensely obstructive in the one case it is wrong — a deliberate re-shoot of an
existing tray, where every item raises it. The escape hatches must therefore be
reliable, and two of their failure modes are silent:

  * a switch that reports success but stored the opposite value leaves
    duplicate protection off while the UI shows it on;
  * a clear that reports success for a folder it does not know leaves the user
    believing a tray was forgotten when nothing happened.

Both are asserted here. Every test runs against a temp dedup store — none of
them touch the real capture_dedup.json.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


@pytest.fixture
def ct(tmp_path, monkeypatch):
    """capture_tool with its dedup store redirected into tmp_path."""
    import capture_tool as _ct
    dedup = tmp_path / "capture_dedup.json"
    settings = tmp_path / "capture_dedup_settings.json"
    monkeypatch.setattr(_ct, "DEDUP_PATH", str(dedup))
    monkeypatch.setattr(_ct, "DEDUP_SETTINGS_PATH", str(settings))
    monkeypatch.setattr(_ct, "CAPTURE_ROOT", str(tmp_path / "capture_intake"))
    monkeypatch.setattr(_ct, "TRAY_STATE_PATH", str(tmp_path / "capture_current_tray.json"))
    Path(_ct.CAPTURE_ROOT).mkdir()
    import capture_purge
    monkeypatch.setattr(
        capture_purge,
        "_folder_roots",
        lambda capture_tool: {"capture_intake": Path(capture_tool.CAPTURE_ROOT)},
    )
    monkeypatch.setattr(
        capture_purge,
        "_generated_roots",
        lambda: (tmp_path / "output",),
    )
    monkeypatch.setattr(capture_purge, "_record_purge_tombstone", lambda **kwargs: None)
    dedup.write_text(json.dumps({
        "ER22/1": {"folder": "Earrings 1", "filename": "ER22_1.jpg"},
        "ER22/2": {"folder": "Earrings 1", "filename": "ER22_2.jpg"},
        "LR22/9": {"folder": "Rings 3",    "filename": "LR22_9.jpg"},
    }), encoding="utf-8")
    return _ct


@pytest.fixture
def client(ct):
    import capture_server
    capture_server.app.config["TESTING"] = True
    c = capture_server.app.test_client()
    with c.session_transaction() as s:
        s["authed"] = True          # routes are behind login; this is not the SUT
    return c


# ── master switch ────────────────────────────────────────────────────────────

def test_switch_defaults_on(ct):
    """Silently not checking for duplicates is a worse failure than being asked
    to confirm one, so a missing/corrupt settings file must read as ON."""
    assert ct.dedup_enabled() is True


def test_switch_persists_both_ways(ct):
    ct.set_dedup_enabled(False)
    assert ct.dedup_enabled() is False
    ct.set_dedup_enabled(True)
    assert ct.dedup_enabled() is True


def test_switch_off_stops_blocking_but_keeps_recording(ct):
    """The records must survive the switch — otherwise turning blocking off for
    one re-shoot would destroy the history that per-folder clearing needs."""
    assert ct.check_duplicate("ER22/1") is not None
    ct.set_dedup_enabled(False)
    assert ct.check_duplicate("ER22/1") is None, "switch off must not block"
    assert len(ct.dedup_folders()) == 2, "records must still be there"
    ct.set_dedup_enabled(True)
    assert ct.check_duplicate("ER22/1") is not None, "switch on must block again"


@pytest.mark.parametrize("sent,expected", [
    ("1", True), ("true", True), ("on", True), ("yes", True),
    ("0", False), ("false", False), ("off", False), ("no", False),
])
def test_toggle_route_parses_value_explicitly(client, ct, sent, expected):
    """The string "false" is TRUTHY in Python. A truthiness check here turns the
    switch ON when the user asked for OFF, and reports success doing it."""
    r = client.post("/api/capture/memory/toggle", data={"enabled": sent})
    assert r.status_code == 200
    assert r.get_json()["enabled"] is expected
    assert ct.dedup_enabled() is expected, "route must persist what it reported"


def test_toggle_route_rejects_garbage(client, ct):
    r = client.post("/api/capture/memory/toggle", data={"enabled": "maybe"})
    assert r.status_code == 400
    assert ct.dedup_enabled() is True, "a rejected request must change nothing"


# ── per-folder clearing ──────────────────────────────────────────────────────

def test_folders_are_listed_from_records_not_disk(ct):
    """A tray can be deleted off disk while its records linger — which is
    exactly when "already captured" blocks a re-shoot of something that no
    longer exists. Listing from disk would make those folders unclearable."""
    folders = {f["folder"]: f["records"] for f in ct.dedup_folders()}
    assert folders == {"Earrings 1": 2, "Rings 3": 1}


def test_clear_folder_removes_only_that_folder(ct):
    out = ct.clear_folder_memory("Earrings 1")
    assert out["ok"] and out["removed"] == 2
    assert ct.check_duplicate("ER22/1") is None, "cleared tag must be recapturable"
    assert ct.check_duplicate("LR22/9") is not None, "other folders must survive"


def test_clear_folder_never_touches_images(ct, tmp_path, monkeypatch):
    """Forgetting and deleting are separate decisions. Conflating them would
    make a routine "let me re-shoot this tray" quietly destroy the photos."""
    root = tmp_path / "capture_intake" / "Earrings 1"
    root.mkdir(parents=True)
    photo = root / "ER22_1.jpg"
    photo.write_bytes(b"not-really-a-jpeg")
    monkeypatch.setattr(ct, "CAPTURE_ROOT", str(tmp_path / "capture_intake"))
    ct.clear_folder_memory("Earrings 1")
    assert photo.exists(), "clearing memory must never delete captured images"


def test_clear_route_404s_on_unknown_folder(client, ct):
    """Accepting an arbitrary string and reporting removed:0 reads as success
    and hides a typo'd folder name from the user."""
    r = client.post("/api/capture/memory/clear_folder", data={"folder": "Nope 7"})
    assert r.status_code == 404
    assert len(ct.dedup_folders()) == 2, "nothing may be removed on a bad name"


def test_clear_route_rejects_empty_folder(client, ct):
    r = client.post("/api/capture/memory/clear_folder", data={"folder": "  "})
    assert r.status_code == 400
    assert len(ct.dedup_folders()) == 2


def test_clear_route_requires_exact_confirmation(client, ct):
    r = client.post(
        "/api/capture/memory/clear_folder",
        data={"folder": "Earrings 1"},
    )
    assert r.status_code == 400
    assert len(ct.dedup_folders()) == 2

    r = client.post(
        "/api/capture/memory/clear_folder",
        data={"folder": "Earrings 1", "confirm_folder": "Rings 3"},
    )
    assert r.status_code == 400
    assert len(ct.dedup_folders()) == 2


def test_clear_route_preserves_master_capture(client, ct):
    folder = Path(ct.CAPTURE_ROOT) / "Earrings 1"
    folder.mkdir()
    (folder / "ER22_1.jpg").write_bytes(b"capture")
    r = client.post(
        "/api/capture/memory/clear_folder",
        data={"folder": "Earrings 1", "confirm_folder": "Earrings 1"},
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert folder.exists()
    assert (folder / "ER22_1.jpg").read_bytes() == b"capture"
    assert r.get_json()["preserved_master_files"] == 1
    assert {f["folder"] for f in ct.dedup_folders()} == {"Rings 3"}


def test_memory_route_reports_switch_and_folders(client):
    d = client.get("/api/capture/memory").get_json()
    assert d["enabled"] is True
    assert {f["folder"] for f in d["folders"]} == {"Earrings 1", "Rings 3"}
