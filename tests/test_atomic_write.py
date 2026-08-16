"""
Tests for the atomic-write helpers added during the reliability hardening
pass — a crash mid-write must never leave a truncated/corrupt JSON file.

The old per-pair "progress_<category>.json" model (app._save_progress /
_load_progress / _clear_progress / _atomic_write_json) was dropped when the
capture model moved to pre-labeled files at capture time (see
review_queue.py / processed_state.py) — no more per-pair-number progress
tracking needed. Those tests removed with it; only the still-current,
self-contained catalogue_db round-trip test remains.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import catalogue_db


def test_catalogue_db_save_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(catalogue_db, "DB_PATH", str(tmp_path / "catalogue_db.json"))
    monkeypatch.setattr(catalogue_db, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(catalogue_db, "OFFSITE_BACKUP_DIR", str(tmp_path / "does_not_exist" / "offsite"))
    db = {"entries": [{"label": "TP22/1", "ts": 1000.0}]}
    catalogue_db._save(db)
    loaded = catalogue_db._load()
    assert loaded == db
