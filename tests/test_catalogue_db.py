"""
Tests for catalogue_db's pruning and record/check-only split — the
check_only vs check_and_record distinction is what fixed the "retried pair
flags itself as a duplicate of its own failed attempt" bug this session.
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import catalogue_db


def test_prune_removes_entries_older_than_keep_days():
    now = time.time()
    db = {"entries": [
        {"label": "OLD", "ts": now - (catalogue_db.KEEP_DAYS + 5) * 86400},
        {"label": "RECENT", "ts": now - 86400},
    ]}
    pruned = catalogue_db._prune(db)
    labels = [e["label"] for e in pruned["entries"]]
    assert labels == ["RECENT"]


def test_prune_keeps_entries_within_window():
    now = time.time()
    db = {"entries": [{"label": "A", "ts": now - 86400}, {"label": "B", "ts": now}]}
    pruned = catalogue_db._prune(db)
    assert len(pruned["entries"]) == 2


def test_prune_handles_missing_ts_as_epoch_zero():
    db = {"entries": [{"label": "NO_TS"}]}
    pruned = catalogue_db._prune(db)
    assert pruned["entries"] == []  # ts defaults to 0 -> always older than cutoff


def test_check_only_does_not_record(tmp_path, monkeypatch):
    monkeypatch.setattr(catalogue_db, "DB_PATH", str(tmp_path / "catalogue_db.json"))
    monkeypatch.setattr(catalogue_db, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(catalogue_db, "OFFSITE_BACKUP_DIR", str(tmp_path / "does_not_exist" / "offsite"))

    findings = catalogue_db.check_only("TP22/1", "/nonexistent/output.jpg", "earrings")
    assert findings == []
    # Nothing should have been written — the whole point of check_only is
    # that a not-yet-successful pair doesn't get permanently recorded.
    assert not os.path.exists(catalogue_db.DB_PATH)


def test_check_and_record_persists_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(catalogue_db, "DB_PATH", str(tmp_path / "catalogue_db.json"))
    monkeypatch.setattr(catalogue_db, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(catalogue_db, "OFFSITE_BACKUP_DIR", str(tmp_path / "does_not_exist" / "offsite"))

    catalogue_db.check_and_record("TP22/1", "/nonexistent/output.jpg", "earrings")
    assert os.path.exists(catalogue_db.DB_PATH)
    db = catalogue_db._load()
    assert len(db["entries"]) == 1
    assert db["entries"][0]["label"] == "TP22/1"


def test_retry_after_check_only_does_not_flag_self_as_duplicate(tmp_path, monkeypatch):
    """
    Regression test for the exact bug fixed this session: a pair whose
    model shoot fails calls check_only (not recorded); on retry, check_only
    runs again and must NOT see its own prior attempt as a duplicate,
    because check_only never wrote anything the first time.
    """
    monkeypatch.setattr(catalogue_db, "DB_PATH", str(tmp_path / "catalogue_db.json"))
    monkeypatch.setattr(catalogue_db, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(catalogue_db, "OFFSITE_BACKUP_DIR", str(tmp_path / "does_not_exist" / "offsite"))

    findings_first = catalogue_db.check_only("TP22/5", "/nonexistent/a.jpg", "earrings")
    findings_retry = catalogue_db.check_only("TP22/5", "/nonexistent/a.jpg", "earrings")
    assert findings_first == []
    assert findings_retry == []  # would contain an "exact_duplicate" finding if the bug regressed


def test_hash_dist_identical_hashes_is_zero():
    import imagehash
    h = str(imagehash.hex_to_hash("ffffffffffffffff"))
    assert catalogue_db._hash_dist(h, h) == 0


def test_hash_dist_invalid_input_returns_large_sentinel():
    assert catalogue_db._hash_dist("not_a_hash", "also_not_a_hash") == 999
