import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tray_sequence_migration as migration


def _tray(root: Path, name: str, *, folder_ns: int, image_ns: int | None = None) -> Path:
    # Windows does not reliably preserve timestamps only a few nanoseconds
    # after the Unix epoch.  Keep the fixtures modern while retaining simple
    # relative ordering in each test.
    epoch = 1_700_000_000_000_000_000
    tray = root / name
    tray.mkdir()
    if image_ns is not None:
        image = tray / f"{name.replace(' ', '_')}.jpg"
        image.write_bytes(b"primary")
        value = epoch + image_ns * 1_000_000_000
        os.utime(image, ns=(value, value))
    value = epoch + folder_ns * 1_000_000_000
    os.utime(tray, ns=(value, value))
    return tray


def _metadata(tmp_path: Path, state: dict, dedup: dict) -> tuple[Path, Path]:
    state_path = tmp_path / "capture_current_tray.json"
    dedup_path = tmp_path / "capture_dedup.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    dedup_path.write_text(json.dumps(dedup), encoding="utf-8")
    return state_path, dedup_path


def test_discovery_excludes_hidden_and_practice_folders(tmp_path):
    _tray(tmp_path, "Ladies Rings 1", folder_ns=10)
    _tray(tmp_path, "_TEST", folder_ns=1)
    _tray(tmp_path, ".scratch", folder_ns=1)
    _tray(tmp_path, "Test Practice 1", folder_ns=1)
    (tmp_path / "not-a-folder.txt").write_text("x", encoding="utf-8")

    found, excluded = migration.discover_top_level_trays(tmp_path)

    assert [path.name for path in found] == ["Ladies Rings 1"]
    assert set(excluded) == {"_TEST", ".scratch", "Test Practice 1"}


def test_order_uses_earliest_primary_image_then_folder_fallback(tmp_path):
    first = _tray(tmp_path, "Earrings 8", folder_ns=900, image_ns=100)
    archive = first / "_tag_archive"
    archive.mkdir()
    tag = archive / "ER_tag.jpg"
    tag.write_bytes(b"tag")
    os.utime(tag, ns=(1, 1))
    _tray(tmp_path, "Ladies Rings 3", folder_ns=200, image_ns=300)
    _tray(tmp_path, "Locket 4", folder_ns=250)

    plan = migration.build_plan(tmp_path)

    assert plan.safe
    assert [(row.source_name, row.target_name) for row in plan.trays] == [
        ("Earrings 8", "1 Earrings"),
        ("Locket 4", "2 Locket"),
        ("Ladies Rings 3", "3 Ladies Rings"),
    ]
    assert [row.timestamp_source for row in plan.trays] == [
        "primary_image",
        "folder",
        "primary_image",
    ]


def test_existing_global_names_are_resequenced_gaplessly(tmp_path):
    _tray(tmp_path, "20 Pendant", folder_ns=20, image_ns=20)
    _tray(tmp_path, "Necklace 99", folder_ns=10, image_ns=10)

    plan = migration.build_plan(tmp_path)

    assert [row.target_name for row in plan.trays] == ["1 Necklace", "2 Pendant"]


@pytest.mark.parametrize("name", ["Unnumbered", "1 Ladies Rings 2"])
def test_ambiguous_labels_make_plan_unsafe(tmp_path, name):
    _tray(tmp_path, name, folder_ns=1)

    plan = migration.build_plan(tmp_path)

    assert not plan.safe
    assert "unsafe tray label" in plan.issues[0]


def test_gauge_suffixed_stock_category_resolves_as_leading_not_ambiguous(tmp_path):
    """"34 LOCKET 22" matches both the leading-global and trailing-legacy
    patterns at once (the "22" could be a legacy per-category counter or the
    real gauge suffix of stock_category_map's "LOCKET 22"). It must resolve
    as leading + the full "LOCKET 22" label, not be refused as ambiguous —
    "34 LOCKET" is not a real category, but "LOCKET 22" is."""
    _tray(tmp_path, "34 LOCKET 22", folder_ns=1)

    plan = migration.build_plan(tmp_path)

    assert plan.safe, plan.issues
    assert plan.trays[0].category_label == "LOCKET 22"
    assert plan.trays[0].target_name == "1 LOCKET 22"


def test_gauge_suffixed_ambiguity_still_refused_when_neither_side_is_a_known_label(tmp_path):
    """Sanity check that the new disambiguation doesn't over-fire: a folder
    matching both patterns where NEITHER remainder is a real stock category
    (e.g. "1 Ladies Rings 2") must still be refused as genuinely ambiguous."""
    _tray(tmp_path, "1 Ladies Rings 2", folder_ns=1)

    plan = migration.build_plan(tmp_path)

    assert not plan.safe
    assert "unsafe tray label" in plan.issues[0]


def test_case_variant_category_labels_are_rejected(tmp_path):
    _tray(tmp_path, "Earrings 1", folder_ns=1)
    _tray(tmp_path, "earrings 2", folder_ns=2)

    plan = migration.build_plan(tmp_path)

    assert not plan.safe
    assert any("ambiguous category spelling" in issue for issue in plan.issues)


def test_target_collision_with_unmanaged_entry_is_rejected(tmp_path):
    _tray(tmp_path, "Earrings 9", folder_ns=1)
    (tmp_path / "1 Earrings").write_text("occupied", encoding="utf-8")

    plan = migration.build_plan(tmp_path)

    assert not plan.safe
    assert any("collides with existing entry" in issue for issue in plan.issues)


def test_preview_formats_are_read_only(tmp_path):
    tray = _tray(tmp_path, "Locket 7", folder_ns=50, image_ns=40)
    before = sorted(path.name for path in tmp_path.iterdir())

    plan = migration.build_plan(tmp_path)
    text = migration.render_text(plan)
    payload = json.loads(migration.render_json(plan))

    assert sorted(path.name for path in tmp_path.iterdir()) == before
    assert tray.exists()
    assert "Writes performed: NO" in text
    assert payload["writes_performed"] is False
    assert payload["mapping"][0]["target_name"] == "1 Locket"


def test_apply_requires_both_exact_safety_gates(tmp_path):
    _tray(tmp_path, "Locket 7", folder_ns=1)
    plan = migration.build_plan(tmp_path)
    state, dedup = _metadata(tmp_path, {}, {})

    with pytest.raises(migration.MigrationGateError):
        migration.apply_plan(
            plan,
            confirmation="yes",
            capture_stopped_assertion=True,
            state_path=state,
            dedup_path=dedup,
        )
    with pytest.raises(migration.MigrationGateError):
        migration.apply_plan(
            plan,
            confirmation=migration.APPLY_CONFIRMATION,
            capture_stopped_assertion=False,
            state_path=state,
            dedup_path=dedup,
        )
    assert (tmp_path / "Locket 7").is_dir()


def test_apply_uses_collision_safe_two_phase_rename_and_rewrites_metadata(tmp_path):
    # The first target already exists as another managed source, so direct
    # one-by-one renames would fail or overwrite; two-phase staging is needed.
    older = _tray(tmp_path, "Earrings 9", folder_ns=1, image_ns=1)
    newer = _tray(tmp_path, "1 Earrings", folder_ns=2, image_ns=2)
    (older / "old.txt").write_text("older", encoding="utf-8")
    (newer / "new.txt").write_text("newer", encoding="utf-8")
    state, dedup = _metadata(
        tmp_path,
        {"earrings": "1 Earrings"},
        {
            "ER/1": {"folder": "Earrings 9", "filename": "ER_1.jpg"},
            "ER/2": {"folder": "1 Earrings", "filename": "ER_2.jpg"},
        },
    )
    plan = migration.build_plan(tmp_path)
    assert plan.safe

    result = migration.apply_plan(
        plan,
        confirmation=migration.APPLY_CONFIRMATION,
        capture_stopped_assertion=True,
        state_path=state,
        dedup_path=dedup,
    )

    assert result.renamed_directories == 2
    assert (tmp_path / "1 Earrings" / "old.txt").read_text(encoding="utf-8") == "older"
    assert (tmp_path / "2 Earrings" / "new.txt").read_text(encoding="utf-8") == "newer"
    assert json.loads(state.read_text(encoding="utf-8")) == {"earrings": "2 Earrings"}
    updated = json.loads(dedup.read_text(encoding="utf-8"))
    assert updated["ER/1"]["folder"] == "1 Earrings"
    assert updated["ER/2"]["folder"] == "2 Earrings"
    assert not list(tmp_path.glob(".tray-sequence-*"))


def test_apply_refuses_stale_plan_before_any_write(tmp_path):
    _tray(tmp_path, "Locket 7", folder_ns=1, image_ns=1)
    plan = migration.build_plan(tmp_path)
    state, dedup = _metadata(tmp_path, {}, {})
    _tray(tmp_path, "Pendant 1", folder_ns=2, image_ns=2)

    with pytest.raises(migration.StalePlanError):
        migration.apply_plan(
            plan,
            confirmation=migration.APPLY_CONFIRMATION,
            capture_stopped_assertion=True,
            state_path=state,
            dedup_path=dedup,
        )

    assert (tmp_path / "Locket 7").is_dir()
    assert (tmp_path / "Pendant 1").is_dir()


def test_bad_metadata_is_rejected_before_directory_renames(tmp_path):
    _tray(tmp_path, "Locket 7", folder_ns=1)
    plan = migration.build_plan(tmp_path)
    state, dedup = _metadata(tmp_path, {}, {})
    dedup.write_text("not-json", encoding="utf-8")

    with pytest.raises(migration.MigrationError, match="Cannot read capture dedup"):
        migration.apply_plan(
            plan,
            confirmation=migration.APPLY_CONFIRMATION,
            capture_stopped_assertion=True,
            state_path=state,
            dedup_path=dedup,
        )

    assert (tmp_path / "Locket 7").is_dir()
