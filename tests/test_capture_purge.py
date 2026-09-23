import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import capture_purge
import capture_tool


@pytest.fixture
def purge_env(tmp_path, monkeypatch):
    roots = {
        "capture_intake": tmp_path / "capture_intake",
        "capture": tmp_path / "capture",
        "processing": tmp_path / "processing",
        "processed": tmp_path / "processed",
        "needs_review": tmp_path / "needs_review",
        "rejected": tmp_path / "rejected",
        "raw_mirror": tmp_path / "raw_mirror",
    }
    for root in roots.values():
        root.mkdir()
    output = tmp_path / "output"
    legacy_output = tmp_path / "output_aradhana"
    output.mkdir()
    legacy_output.mkdir()

    dedup = tmp_path / "capture_dedup.json"
    state = tmp_path / "capture_current_tray.json"
    monkeypatch.setattr(capture_tool, "CAPTURE_ROOT", str(roots["capture_intake"]))
    monkeypatch.setattr(capture_tool, "DEDUP_PATH", str(dedup))
    monkeypatch.setattr(capture_tool, "TRAY_STATE_PATH", str(state))
    monkeypatch.setattr(capture_purge, "_folder_roots", lambda ct: roots)
    monkeypatch.setattr(
        capture_purge,
        "_generated_roots",
        lambda: (output, legacy_output),
    )
    monkeypatch.setattr(capture_purge, "_record_purge_tombstone", lambda **kwargs: None)
    dedup.write_text("{}", encoding="utf-8")
    state.write_text("{}", encoding="utf-8")
    return roots, output, legacy_output, dedup, state


def _write_session(root: Path, folder: str, tag: str) -> None:
    session = root / folder
    archive = session / capture_tool.TAG_ARCHIVE_DIRNAME
    archive.mkdir(parents=True)
    (session / f"{tag}.jpg").write_bytes(b"primary")
    (archive / f"{tag}_tag.jpg").write_bytes(b"tag")


def test_confirmed_purge_preserves_master_and_removes_downstream(purge_env):
    roots, output, legacy_output, dedup, state = purge_env
    for root in roots.values():
        _write_session(root, "Earrings 1", "ER22_1")
    for generated_root in (output, legacy_output):
        variety = generated_root / "FANCY"
        variety.mkdir()
        (variety / "ER22_1.jpg").write_bytes(b"studio")
        (variety / "ER22_1_2.jpg").write_bytes(b"model")
    dedup.write_text(json.dumps({
        "ER22/1": {
            "folder": "Earrings 1",
            "filename": "ER22_1.jpg",
        },
        "LR22/9": {
            "folder": "Rings 3",
            "filename": "LR22_9.jpg",
        },
    }), encoding="utf-8")
    state.write_text(json.dumps({"earrings": "Earrings 1"}), encoding="utf-8")

    preview = capture_purge.preview_folder_history(capture_tool, "Earrings 1")
    immutable = {"capture_intake", "capture", "raw_mirror"}
    assert preview.files == (len(roots) - len(immutable)) * 2 + 4
    assert preview.preserved_master_files == len(immutable) * 2
    assert preview.active_categories == ("earrings",)

    result = capture_purge.purge_folder_history(capture_tool, "Earrings 1")

    assert result["ok"] is True
    # Global tray numbering (capture_tool._next_tray_number, changed
    # 2026-07-31 alongside tray_sequence_migration.py): the next tray is
    # "<N> <Label>", N being the highest number across EVERY category's
    # folders plus one — not the old per-category "<Label> <N>" scheme. In
    # this isolated fixture no other numbered folder exists, so N is 1.
    assert result["advanced_trays"] == {"earrings": "1 Earrings"}
    for name, root in roots.items():
        assert (root / "Earrings 1").exists() is (name in immutable)
    assert not list(output.rglob("ER22_1*.jpg"))
    assert not list(legacy_output.rglob("ER22_1*.jpg"))
    # 2026-08-01: the advanced tray is reserved in state but its folder is
    # deliberately not created until a real capture lands in it — otherwise
    # every Forget of an active tray would immediately manifest a fresh
    # empty folder in capture_intake in its place.
    assert not (roots["capture_intake"] / "1 Earrings").exists()
    assert json.loads(state.read_text(encoding="utf-8")) == {
        "earrings": "1 Earrings"
    }
    remaining = json.loads(dedup.read_text(encoding="utf-8"))
    assert set(remaining) == {"LR22/9"}


def test_generated_output_is_preserved_when_tag_exists_in_another_folder(purge_env):
    roots, output, _, dedup, _ = purge_env
    _write_session(roots["capture_intake"], "Earrings 1", "ER22_1")
    _write_session(roots["capture_intake"], "Earrings 2", "ER22_1")
    variety = output / "FANCY"
    variety.mkdir()
    generated = variety / "ER22_1.jpg"
    generated.write_bytes(b"shared")
    dedup.write_text(json.dumps({
        "ER22/1": {"folder": "Earrings 1", "filename": "ER22_1.jpg"},
    }), encoding="utf-8")

    result = capture_purge.purge_folder_history(capture_tool, "Earrings 1")

    assert result["ok"] is True
    assert result["shared_tags_preserved"] == ["ER22_1"]
    assert generated.exists()
    assert (roots["capture_intake"] / "Earrings 1").exists()
    assert (roots["capture_intake"] / "Earrings 2").exists()


def test_list_capture_histories_counts_match_a_real_folder(purge_env):
    """The listing's per-folder counts must agree with what a full purge
    preview would report for that same folder — it's just computed without
    the expensive cross-folder shared-tag pass."""
    roots, *_, dedup, _ = purge_env
    _write_session(roots["capture_intake"], "Earrings 1", "ER22_1")
    session = roots["capture_intake"] / "Earrings 1"
    (session / "ER22_2.jpg").write_bytes(b"primary")
    (session / capture_tool.TAG_ARCHIVE_DIRNAME / "ER22_2_tag.jpg").write_bytes(b"tag")
    dedup.write_text(json.dumps({
        "ER22/1": {"folder": "Earrings 1", "filename": "ER22_1.jpg"},
        "ER22/2": {"folder": "Earrings 1", "filename": "ER22_2.jpg"},
    }), encoding="utf-8")

    histories = {row["folder"]: row for row in capture_purge.list_capture_histories(capture_tool)}

    assert histories["Earrings 1"]["records"] == 2
    assert histories["Earrings 1"]["primary_images"] == 2
    assert histories["Earrings 1"]["files"] == 4  # 2 primary + 2 archived tags


def test_list_capture_histories_never_scans_other_folders(purge_env, monkeypatch):
    """2026-08-01: list_capture_histories used to call the full purge-preview
    per folder, which cross-references every OTHER folder via
    _shared_tag_stems/_generated_files — confirmed live at 24s for 138
    folders. The listing must stay O(n) in folder count: no cross-folder
    scan may run just to build this summary."""
    roots, *_ = purge_env
    _write_session(roots["capture_intake"], "Earrings 1", "ER22_1")
    _write_session(roots["capture_intake"], "Earrings 2", "ER22_2")

    def _boom(*a, **k):
        raise AssertionError("list_capture_histories must not cross-reference folders")

    monkeypatch.setattr(capture_purge, "_shared_tag_stems", _boom)
    monkeypatch.setattr(capture_purge, "_generated_files", _boom)

    histories = capture_purge.list_capture_histories(capture_tool)

    assert {row["folder"] for row in histories} == {"Earrings 1", "Earrings 2"}


def test_list_capture_histories_omits_truly_empty_folders(purge_env):
    """A folder with no dedup records and no files is noise in an admin
    list meant to show what can be forgotten — nothing there to forget."""
    roots, *_ = purge_env
    (roots["capture_intake"] / "Empty 1").mkdir()
    _write_session(roots["capture_intake"], "Earrings 1", "ER22_1")

    histories = capture_purge.list_capture_histories(capture_tool)

    assert {row["folder"] for row in histories} == {"Earrings 1"}


@pytest.mark.parametrize("folder", ["", ".", "..", "../Earrings 1", r"..\Earrings 1"])
def test_unsafe_folder_names_are_rejected_without_deleting(purge_env, folder):
    roots, *_ = purge_env
    keep = roots["capture_intake"] / "Keep 1"
    keep.mkdir()

    with pytest.raises(capture_purge.CapturePurgeError):
        capture_purge.preview_folder_history(capture_tool, folder)

    assert keep.exists()


def test_failed_folder_delete_keeps_dedup_history(purge_env, monkeypatch):
    roots, _, _, dedup, _ = purge_env
    _write_session(roots["capture_intake"], "Earrings 1", "ER22_1")
    _write_session(roots["processing"], "Earrings 1", "ER22_1")
    dedup.write_text(json.dumps({
        "ER22/1": {"folder": "Earrings 1", "filename": "ER22_1.jpg"},
    }), encoding="utf-8")

    def fail_delete(path):
        raise PermissionError("locked")

    monkeypatch.setattr(capture_purge.shutil, "rmtree", fail_delete)
    result = capture_purge.purge_folder_history(capture_tool, "Earrings 1")

    assert result["ok"] is False
    assert "ER22/1" in json.loads(dedup.read_text(encoding="utf-8"))
    assert (roots["capture_intake"] / "Earrings 1").exists()
