"""
find_item/delete_item (capture_tool.py) and their routes: 2026-08-01
replacement for whole-folder Forget — search one item by its exact tag
code, review it, delete just that item's jewel+tag photo and dedup
record, leaving everything else in the folder untouched.
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
    monkeypatch.setattr(_ct, "DEDUP_PATH", str(dedup))
    monkeypatch.setattr(_ct, "CAPTURE_ROOT", str(tmp_path / "capture_intake"))
    monkeypatch.setattr(_ct, "TRAY_STATE_PATH", str(tmp_path / "capture_current_tray.json"))
    root = Path(_ct.CAPTURE_ROOT)
    root.mkdir()
    folder = root / "1 GENTS RING 22"
    (folder / _ct.TAG_ARCHIVE_DIRNAME).mkdir(parents=True)
    (folder / "GR22_1.jpg").write_bytes(b"jewel")
    (folder / _ct.TAG_ARCHIVE_DIRNAME / "GR22_1_tag.jpg").write_bytes(b"tag")
    (folder / "GR22_2.jpg").write_bytes(b"jewel2")
    (folder / _ct.TAG_ARCHIVE_DIRNAME / "GR22_2_tag.jpg").write_bytes(b"tag2")
    dedup.write_text(json.dumps({
        "GR22/1": {"folder": "1 GENTS RING 22", "filename": "GR22_1.jpg", "category": "gents_ring_22", "ts": 1},
        "GR22/2": {"folder": "1 GENTS RING 22", "filename": "GR22_2.jpg", "category": "gents_ring_22", "ts": 2},
    }), encoding="utf-8")
    return _ct


@pytest.fixture
def client(ct):
    import capture_server
    capture_server.app.config["TESTING"] = True
    c = capture_server.app.test_client()
    with c.session_transaction() as s:
        s["authed"] = True
    return c


def test_find_item_returns_the_matching_record(ct):
    item = ct.find_item("GR22/1")
    assert item["folder"] == "1 GENTS RING 22"
    assert item["filename"] == "GR22_1.jpg"
    assert item["jewel_exists"] is True
    assert item["tag_exists"] is True


def test_find_item_returns_none_for_unknown_tag(ct):
    assert ct.find_item("ZZ99/1") is None


def test_delete_item_removes_only_that_items_files(ct):
    root = Path(ct.CAPTURE_ROOT) / "1 GENTS RING 22"
    result = ct.delete_item("GR22/1")

    assert result["ok"] is True
    assert result["deleted_files"] == 2
    assert not (root / "GR22_1.jpg").exists()
    assert not (root / ct.TAG_ARCHIVE_DIRNAME / "GR22_1_tag.jpg").exists()
    # the other item in the same folder is completely untouched
    assert (root / "GR22_2.jpg").exists()
    assert (root / ct.TAG_ARCHIVE_DIRNAME / "GR22_2_tag.jpg").exists()


def test_delete_item_removes_only_that_tags_dedup_record(ct):
    ct.delete_item("GR22/1")

    dedup = json.loads(Path(ct.DEDUP_PATH).read_text(encoding="utf-8"))
    assert "GR22/1" not in dedup
    assert "GR22/2" in dedup


def test_delete_item_resets_duplicate_blocking_for_that_tag_only(ct):
    assert ct.check_duplicate("GR22/1") is not None
    ct.delete_item("GR22/1")
    assert ct.check_duplicate("GR22/1") is None
    assert ct.check_duplicate("GR22/2") is not None


def test_delete_item_fails_cleanly_for_unknown_tag(ct):
    result = ct.delete_item("ZZ99/1")
    assert result["ok"] is False


def test_search_item_route_finds_a_real_item(client, ct):
    r = client.get("/api/capture/search_item?tag_code=GR22/1")
    assert r.status_code == 200
    assert r.get_json()["item"]["folder"] == "1 GENTS RING 22"


def test_search_item_route_404s_for_unknown_tag(client, ct):
    r = client.get("/api/capture/search_item?tag_code=ZZ99/1")
    assert r.status_code == 404


def test_delete_item_route_requires_exact_confirmation(client, ct):
    r = client.post("/api/capture/delete_item", data={"tag_code": "GR22/1"})
    assert r.status_code == 400
    assert ct.find_item("GR22/1") is not None

    r = client.post("/api/capture/delete_item", data={
        "tag_code": "GR22/1", "confirm_tag_code": "GR22/2",
    })
    assert r.status_code == 400
    assert ct.find_item("GR22/1") is not None


def test_delete_item_route_deletes_on_exact_confirmation(client, ct):
    r = client.post("/api/capture/delete_item", data={
        "tag_code": "GR22/1", "confirm_tag_code": "GR22/1",
    })
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert ct.find_item("GR22/1") is None
    assert ct.find_item("GR22/2") is not None
