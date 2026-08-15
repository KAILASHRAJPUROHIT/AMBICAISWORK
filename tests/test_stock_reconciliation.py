import json
from pathlib import Path

import pytest

import stock_reconciliation as sr


def _fake_pair(tmp_path, monkeypatch, previous, current):
    stock_dir = tmp_path / "Stock"
    stock_dir.mkdir()
    old = stock_dir / "01082026.xls"
    new = stock_dir / "02082026.xls"
    old.write_bytes(b"old-stock")
    new.write_bytes(b"new-stock")
    monkeypatch.setattr(sr, "_candidate_pair", lambda _path: (old, new))
    monkeypatch.setattr(
        sr,
        "_validated_pair",
        lambda _path: (old, new, dict(previous), dict(current)),
    )
    return stock_dir


def test_reconcile_moves_sold_files_and_memory_but_preserves_current_prefix(
    tmp_path, monkeypatch
):
    previous = {
        "LR22_1": "LR22/1",
        "LR22_11": "LR22/11",
        "JB22_3": "JB22/3",
    }
    current = {"LR22_11": "LR22/11", "JB22_4": "JB22/4"}
    stock_dir = _fake_pair(tmp_path, monkeypatch, previous, current)
    raw = tmp_path / "capture_intake" / "1 LADIES RING 22"
    output = tmp_path / "output" / "REGULAR"
    raw.mkdir(parents=True)
    output.mkdir(parents=True)
    (raw / "LR22_1.jpg").write_bytes(b"sold")
    (raw / "LR22_1_2.jpg").write_bytes(b"sold-variant")
    (raw / "LR22_11.jpg").write_bytes(b"current")
    (output / "JB22_3.jpg").write_bytes(b"sold-output")

    (tmp_path / "capture_dedup.json").write_text(json.dumps({
        "LR22/1": {"folder": raw.name, "filename": "LR22_1.jpg"},
        "LR22/11": {"folder": raw.name, "filename": "LR22_11.jpg"},
    }), encoding="utf-8")
    (tmp_path / "catalogue_db.json").write_text(json.dumps({"entries": [
        {"label": "JB22/3"}, {"label": "LR22/11"},
    ]}), encoding="utf-8")
    (tmp_path / "review_state.json").write_text(
        json.dumps({"LR22_1": {"status": "review"}, "LR22_11": {"status": "ok"}}),
        encoding="utf-8",
    )
    (tmp_path / "progress_run.json").write_text(json.dumps({
        "a": {"label": "JB22/3"}, "b": {"label": "LR22/11"},
    }), encoding="utf-8")
    (tmp_path / "feedback.jsonl").write_text(
        json.dumps({"label": "LR22/1"}) + "\n" + json.dumps({"label": "LR22/11"}) + "\n",
        encoding="utf-8",
    )

    state = tmp_path / "stock_reconciliation_state.json"
    result = sr.ensure_reconciled(
        stock_dir=stock_dir,
        base_dir=tmp_path,
        state_path=state,
        roots=(raw.parent.resolve(), output.parent.resolve()),
    )

    assert result.reconciled is True
    assert set(result.sold_tags) == {"LR22_1", "JB22_3"}
    assert result.new_tags == ("JB22_4",)
    assert result.moved_files == 3
    assert result.deleted_files == 0
    assert not (raw / "LR22_1.jpg").exists()
    assert not (raw / "LR22_1_2.jpg").exists()
    assert (raw / "LR22_11.jpg").read_bytes() == b"current"
    assert not (output / "JB22_3.jpg").exists()
    sold_files = sorted(path.name for path in (tmp_path / "sold" / "02082026").rglob("*.jpg"))
    assert sold_files == ["JB22_3.jpg", "LR22_1.jpg", "LR22_1_2.jpg"]
    assert set(json.loads((tmp_path / "capture_dedup.json").read_text())) == {"LR22/11"}
    assert [e["label"] for e in json.loads((tmp_path / "catalogue_db.json").read_text())["entries"]] == ["LR22/11"]
    assert list(json.loads((tmp_path / "review_state.json").read_text())) == ["LR22_11"]
    assert list(json.loads((tmp_path / "progress_run.json").read_text())) == ["b"]
    feedback = [
        json.loads(line)
        for line in (tmp_path / "feedback.jsonl").read_text().splitlines()
    ]
    assert feedback == [{"label": "LR22/11"}]
    backups = list((tmp_path / "backups").iterdir())
    assert len(backups) == 1
    assert "02082026" in backups[0].name

    second = sr.ensure_reconciled(
        stock_dir=stock_dir,
        base_dir=tmp_path,
        state_path=state,
        roots=(raw.parent.resolve(), output.parent.resolve()),
    )
    assert second.reconciled is False
    assert second.moved_files == 3
    assert second.deleted_files == 0


def test_status_lists_every_uncaptured_current_tag_not_only_new_tags(tmp_path, monkeypatch):
    stock_dir = _fake_pair(
        tmp_path, monkeypatch, {"LR22_1": "LR22/1"},
        {"LR22_1": "LR22/1", "JB22_4": "JB22/4"},
    )
    folder = tmp_path / "capture_intake" / "2 JHUMKA 22"
    folder.mkdir(parents=True)
    (folder / "JB22_4.jpg").write_bytes(b"captured")
    (tmp_path / "capture_dedup.json").write_text(json.dumps({
        "JB22/4": {"folder": folder.name, "filename": "JB22_4.jpg"},
    }), encoding="utf-8")
    payload = sr.status(
        stock_dir=stock_dir,
        base_dir=tmp_path,
        state_path=tmp_path / "state.json",
        roots=((tmp_path / "capture_intake").resolve(),),
    )
    assert payload["pending_capture_count"] == 1
    assert [item["safe_tag"] for item in payload["pending_capture"]] == ["LR22_1"]
    assert payload["new_pending_capture_count"] == 0
    assert payload["captured_raw_count"] == 1


def test_reconcile_safety_stops_large_daily_drop(tmp_path, monkeypatch):
    previous = {f"LR22_{n}": f"LR22/{n}" for n in range(sr.MAX_SOLD_TAGS_PER_RUN + 1)}
    stock_dir = _fake_pair(tmp_path, monkeypatch, previous, {"LR22_9999": "LR22/9999"})
    with pytest.raises(sr.StockReconciliationError, match="Safety stop"):
        sr.ensure_reconciled(
            stock_dir=stock_dir,
            base_dir=tmp_path,
            state_path=tmp_path / "state.json",
            roots=(),
        )


def test_capture_recommendations_finish_small_started_categories_first():
    items = [
        {"safe_tag": "A22_1", "label": "A22/1", "category": "Alpha"},
        {"safe_tag": "A22_2", "label": "A22/2", "category": "Alpha"},
        {"safe_tag": "A22_10", "label": "A22/10", "category": "Alpha"},
        {"safe_tag": "B22_1", "label": "B22/1", "category": "Beta"},
        {"safe_tag": "C22_1", "label": "C22/1", "category": "Closed"},
        {"safe_tag": "D22_1", "label": "D22/1", "category": "Dormant"},
    ]
    rows = sr._capture_recommendations(
        items, {"A22_1", "A22_2", "B22_1", "C22_1"}
    )
    assert [row["category"] for row in rows] == ["Alpha", "Dormant"]
    assert rows[0]["started"] is True
    assert rows[0]["remaining"] == 1
    assert rows[0]["next_tag"] == "A22/10"
    assert rows[1]["started"] is False


def test_both_templates_have_bounded_safe_stock_popup():
    base = Path(__file__).resolve().parents[1]
    for name in ("index.html", "capture.html"):
        source = (base / "templates" / name).read_text(encoding="utf-8")
        assert "/api/stock/reconciliation" in source
        assert "new AbortController()" in source
        assert "if (pending) return" in source
        assert "textContent = item.label" in source
        assert "Stock items need capture" in source
        assert "items.slice(0, 200)" not in source
        assert "Search tag or category" in source
        assert "document.createDocumentFragment()" in source
    capture_source = (base / "templates" / "capture.html").read_text(encoding="utf-8")
    assert "Recommended next capture" in capture_source
    assert "window.refreshStockCapturePlan = check" in capture_source
    assert "popup-next-recommendation" in capture_source
    assert "nothing: {label: 'Nothing', zoom: 3.4}" in capture_source
    assert "redmi: {label: 'Redmi Pad', zoom: 2.2}" in capture_source
    assert "focusMode', 'continuous'" in capture_source
    assert "ImageCapture(_cameraTrack)" in capture_source
    assert "window.isSecureContext" in capture_source
    assert "permissionConstraints.zoom = true" in capture_source
    assert "Requested ' + desiredZoom.toFixed(1)" in capture_source
    assert "aradhana_camera_profile_v2" in capture_source
    assert "compactFingerprint" in capture_source
    assert "screen/touch fingerprint" in capture_source
