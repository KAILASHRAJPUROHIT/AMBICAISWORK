"""
Tests for the atomic-write helpers added during the reliability hardening
pass — a crash mid-write must never leave a truncated/corrupt JSON file.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app
import catalogue_db


def test_atomic_write_json_round_trips(tmp_path):
    p = str(tmp_path / "data.json")
    app._atomic_write_json(p, {"a": 1, "b": [1, 2, 3]})
    with open(p) as f:
        assert json.load(f) == {"a": 1, "b": [1, 2, 3]}


def test_atomic_write_json_leaves_no_tmp_file_behind(tmp_path):
    p = str(tmp_path / "data.json")
    app._atomic_write_json(p, {"x": 1})
    assert not os.path.exists(p + ".tmp")


def test_atomic_write_overwrites_existing_file_cleanly(tmp_path):
    p = str(tmp_path / "data.json")
    app._atomic_write_json(p, {"version": 1})
    app._atomic_write_json(p, {"version": 2})
    with open(p) as f:
        assert json.load(f) == {"version": 2}


def test_save_progress_and_load_progress_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "BASE", str(tmp_path))
    app._save_progress("earrings", "1", "TP22/30", "earrings/TP22_30.jpg")
    data = app._load_progress("earrings")
    assert data["1"]["label"] == "TP22/30"
    assert data["1"]["output"] == "earrings/TP22_30.jpg"


def test_load_progress_missing_file_returns_empty_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "BASE", str(tmp_path))
    assert app._load_progress("nonexistent_category") == {}


def test_load_progress_corrupt_file_falls_back_to_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "BASE", str(tmp_path))
    bad_path = tmp_path / "progress_earrings.json"
    bad_path.write_text("{not valid json")
    assert app._load_progress("earrings") == {}


def test_clear_progress_removes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "BASE", str(tmp_path))
    app._save_progress("rings", "1", "AJ-001", "rings/AJ-001.jpg")
    p = tmp_path / "progress_rings.json"
    assert p.exists()
    app._clear_progress("rings")
    assert not p.exists()


def test_clear_progress_missing_file_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "BASE", str(tmp_path))
    app._clear_progress("never_existed")  # must not raise


def test_catalogue_db_save_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(catalogue_db, "DB_PATH", str(tmp_path / "catalogue_db.json"))
    monkeypatch.setattr(catalogue_db, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(catalogue_db, "OFFSITE_BACKUP_DIR", str(tmp_path / "does_not_exist" / "offsite"))
    db = {"entries": [{"label": "TP22/1", "ts": 1000.0}]}
    catalogue_db._save(db)
    loaded = catalogue_db._load()
    assert loaded == db
