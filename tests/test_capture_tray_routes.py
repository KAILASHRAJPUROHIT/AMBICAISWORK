"""
Category validation on the capture tray/save routes.

2026-08-01: /api/capture/start_new_tray, /api/capture/save, and
/api/capture/undo_last never checked the submitted category against
capture_tool.CATEGORY_LABELS — only session_summary did. A stale browser
tab still showing a category from before a taxonomy change (e.g. the
pre-2026-08 legacy keys "earrings"/"gents_rings"/"ladies_rings"/...) could
still POST one of those dead keys straight through, reserving (and, before
tray creation was made lazy, immediately creating on disk) a tray for a
category no longer selectable anywhere in the current UI. This is exactly
how capture_current_tray.json ended up with orphaned legacy entries no
longer present in CATEGORY_LABELS at all.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


@pytest.fixture
def ct(tmp_path, monkeypatch):
    import capture_tool as _ct
    dedup = tmp_path / "capture_dedup.json"
    settings = tmp_path / "capture_dedup_settings.json"
    monkeypatch.setattr(_ct, "DEDUP_PATH", str(dedup))
    monkeypatch.setattr(_ct, "DEDUP_SETTINGS_PATH", str(settings))
    monkeypatch.setattr(_ct, "CAPTURE_ROOT", str(tmp_path / "capture_intake"))
    monkeypatch.setattr(_ct, "TRAY_STATE_PATH", str(tmp_path / "capture_current_tray.json"))
    Path(_ct.CAPTURE_ROOT).mkdir()
    dedup.write_text("{}", encoding="utf-8")
    return _ct


@pytest.fixture
def client(ct):
    import capture_server
    capture_server.app.config["TESTING"] = True
    c = capture_server.app.test_client()
    with c.session_transaction() as s:
        s["authed"] = True
    return c


def test_start_new_tray_rejects_a_legacy_category_not_in_the_current_taxonomy(client, ct):
    r = client.post("/api/capture/start_new_tray", data={"category": "earrings"})

    assert r.status_code == 400
    assert "earrings" in r.get_json()["error"]
    assert not Path(ct.TRAY_STATE_PATH).exists(), "a rejected request must never reserve a tray"


def test_start_new_tray_accepts_a_real_current_category(client, ct):
    real_category = next(iter(ct.CATEGORY_LABELS))

    r = client.post("/api/capture/start_new_tray", data={"category": real_category})

    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_save_rejects_a_legacy_category(client, ct):
    r = client.post("/api/capture/save", data={
        "category": "gents_rings",
        "tag_code": "GR22/1",
        "jewel": (__import__("io").BytesIO(b"jewel"), "jewel.jpg"),
        "tag": (__import__("io").BytesIO(b"tag"), "tag.jpg"),
    }, content_type="multipart/form-data")

    assert r.status_code == 400
    assert "gents_rings" in r.get_json()["error"]


def test_save_auto_resolves_category_from_tag_code_when_none_given(client, ct):
    """2026-08-01: the tag's code is already decoded client-side before this
    request is sent — the operator should never have to also manually pick
    a category the code itself already determines."""
    r = client.post("/api/capture/save", data={
        "tag_code": "GR22/1",
        "jewel": (__import__("io").BytesIO(b"jewel"), "jewel.jpg"),
        "tag": (__import__("io").BytesIO(b"tag"), "tag.jpg"),
    }, content_type="multipart/form-data")

    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "GENTS RING 22" in body["folder"]


def test_save_still_rejects_when_tag_code_has_no_known_prefix(client, ct):
    r = client.post("/api/capture/save", data={
        "tag_code": "ZZ99/1",
        "jewel": (__import__("io").BytesIO(b"jewel"), "jewel.jpg"),
        "tag": (__import__("io").BytesIO(b"tag"), "tag.jpg"),
    }, content_type="multipart/form-data")

    assert r.status_code == 400


def test_resolve_category_returns_the_category_for_a_known_tag_code(client, ct):
    r = client.get("/api/capture/resolve_category?tag_code=GR22/1")

    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["label"] == "GENTS RING 22"
    assert body["key"] == "gents_ring_22"


def test_resolve_category_404s_for_an_unknown_prefix(client, ct):
    r = client.get("/api/capture/resolve_category?tag_code=ZZ99/1")

    assert r.status_code == 404
    assert r.get_json()["ok"] is False


def test_undo_last_rejects_a_legacy_category(client, ct):
    r = client.post("/api/capture/undo_last", data={"category": "ladies_rings"})

    assert r.status_code == 400
    assert "ladies_rings" in r.get_json()["error"]
