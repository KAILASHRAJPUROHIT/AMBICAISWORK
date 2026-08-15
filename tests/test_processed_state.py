from __future__ import annotations

import json
from pathlib import Path

import pytest

import processed_state


def _write_json(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_parse_tag_series_accepts_lists_lines_and_ranges():
    assert processed_state.parse_tag_series(
        "LR22_7, LR22_10\nLR22_40-LR22_42"
    ) == ("LR22_7", "LR22_10", "LR22_40", "LR22_41", "LR22_42")


def test_parse_tag_series_rejects_mixed_prefix_or_backwards_range():
    with pytest.raises(ValueError, match="prefixes differ"):
        processed_state.parse_tag_series("LR22_7-TP22_9")
    with pytest.raises(ValueError, match="backwards"):
        processed_state.parse_tag_series("LR22_9-LR22_7")


def test_record_success_moves_only_queue_source_and_never_master(tmp_path):
    processing = tmp_path / "processing"
    legacy = tmp_path / "input"
    processed = tmp_path / "processed"
    source = legacy / "LR22_7.jpg"
    source.parent.mkdir()
    source.write_bytes(b"ring")

    result = processed_state.record_success(
        str(source), "LR22_7", "ladies_rings",
        processing_root=processing,
        legacy_input_root=legacy,
        processed_root=processed,
    )
    destination = processed / "LADIES RING 22" / "LR22_7.jpg"
    assert result["moved"] is True
    assert destination.read_bytes() == b"ring"
    assert not source.exists()

    master = tmp_path / "capture" / "LR22_8.jpg"
    master.parent.mkdir()
    master.write_bytes(b"master")
    skipped = processed_state.record_success(
        str(master), "LR22_8", "ladies_rings",
        processing_root=processing,
        legacy_input_root=legacy,
        processed_root=processed,
    )
    assert skipped["moved"] is False
    assert master.read_bytes() == b"master"


def test_selective_reset_requeues_source_and_forgets_only_selected_tag(tmp_path):
    base = tmp_path / "tool"
    processing = base / "processing"
    processed = base / "processed"
    selected = processed / "LADIES RING 22" / "LR22_7.jpg"
    other = processed / "TOPS 22" / "TP22_1.jpg"
    selected.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    selected.write_bytes(b"ring")
    other.write_bytes(b"tops")
    _write_json(base / "progress_ladies_rings.json", {
        "1": {"label": "LR22_7", "output": "CASTING/LR22_7.jpg"},
        "2": {"label": "LR22_8", "output": "CASTING/LR22_8.jpg"},
    })
    _write_json(base / "catalogue_db.json", {"entries": [
        {"label": "LR22_7"}, {"label": "LR22_8"},
    ]})

    result = processed_state.apply_reset(
        ("LR22_7",), base_dir=base,
        processing_root=processing, processed_root=processed,
        db_path=base / "catalogue_db.json",
    )

    assert (processing / "LADIES RING 22" / "LR22_7.jpg").read_bytes() == b"ring"
    assert not selected.exists()
    assert other.read_bytes() == b"tops"
    progress = json.loads((base / "progress_ladies_rings.json").read_text())
    database = json.loads((base / "catalogue_db.json").read_text())
    assert [record["label"] for record in progress.values()] == ["LR22_8"]
    assert [entry["label"] for entry in database["entries"]] == ["LR22_8"]
    assert Path(result["backup"]).is_dir()


def test_full_reset_clears_all_memory_without_touching_output_or_capture(tmp_path):
    base = tmp_path / "tool"
    processing = base / "processing"
    processed = base / "processed"
    source = processed / "LADIES RING 22" / "LR22_7.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"ring")
    output = base / "output" / "CASTING" / "LR22_7.jpg"
    capture = base / "capture" / "LR22_7.jpg"
    output.parent.mkdir(parents=True); output.write_bytes(b"finished")
    capture.parent.mkdir(parents=True); capture.write_bytes(b"master")
    _write_json(base / "progress_ladies_rings.json", {
        "1": {"label": "LR22_7", "output": "CASTING/LR22_7.jpg"},
    })
    _write_json(base / "catalogue_db.json", {"entries": [{"label": "LR22_7"}]})

    processed_state.apply_reset(
        None, base_dir=base, processing_root=processing,
        processed_root=processed, db_path=base / "catalogue_db.json",
    )

    assert (processing / "LADIES RING 22" / "LR22_7.jpg").exists()
    assert json.loads((base / "progress_ladies_rings.json").read_text()) == {}
    assert json.loads((base / "catalogue_db.json").read_text())["entries"] == []
    assert output.read_bytes() == b"finished"
    assert capture.read_bytes() == b"master"


def test_reset_conflict_aborts_before_any_move_or_memory_change(tmp_path):
    base = tmp_path / "tool"
    processing = base / "processing"
    processed = base / "processed"
    relative = Path("LADIES RING 22/LR22_7.jpg")
    (processed / relative).parent.mkdir(parents=True)
    (processing / relative).parent.mkdir(parents=True)
    (processed / relative).write_bytes(b"old")
    (processing / relative).write_bytes(b"new")
    _write_json(base / "progress_ladies_rings.json", {
        "1": {"label": "LR22_7", "output": "CASTING/LR22_7.jpg"},
    })
    _write_json(base / "catalogue_db.json", {"entries": [{"label": "LR22_7"}]})

    with pytest.raises(FileExistsError):
        processed_state.apply_reset(
            ("LR22_7",), base_dir=base,
            processing_root=processing, processed_root=processed,
            db_path=base / "catalogue_db.json",
        )

    assert (processed / relative).read_bytes() == b"old"
    assert json.loads((base / "progress_ladies_rings.json").read_text())["1"]["label"] == "LR22_7"
