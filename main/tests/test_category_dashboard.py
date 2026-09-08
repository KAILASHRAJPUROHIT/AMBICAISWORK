import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import category_dashboard
import ornament_code_map as ocm


def test_returns_one_row_per_category():
    rows = category_dashboard.category_breakdown("does-not-exist", "does-not-exist-either")
    assert len(rows) == 57
    assert {r["key"] for r in rows} == {c.key for c in ocm.CATEGORIES}


def test_counts_captured_images_in_the_numbered_folder(tmp_path):
    capture = tmp_path / "capture_intake"
    capture.mkdir()
    folder = capture / "3 BANGLE 22"
    folder.mkdir()
    (folder / "BG22_1.jpg").write_bytes(b"x")
    (folder / "BG22_2.jpg").write_bytes(b"x")
    archive = folder / "_tag_archive"
    archive.mkdir()
    (archive / "BG22_1_tag.jpg").write_bytes(b"x")

    rows = category_dashboard.category_breakdown(str(capture), "does-not-exist")
    row = next(r for r in rows if r["label"] == "BANGLE 22")

    assert row["captured"] == 2
    assert row["folder"] == "3 BANGLE 22"


def test_counts_captured_images_in_live_unnumbered_folder(tmp_path):
    capture = tmp_path / "capture_intake" / "GENTS RING 22"
    capture.mkdir(parents=True)
    (capture / "GR22_100.jpg").write_bytes(b"x")
    (capture / "GR22_101.jpg").write_bytes(b"x")

    rows = category_dashboard.category_breakdown(str(tmp_path / "capture_intake"), "missing")
    row = next(r for r in rows if r["label"] == "GENTS RING 22")

    assert row["captured"] == 2
    assert row["folder"] == "GENTS RING 22"


def test_counts_every_numbered_folder_for_the_same_category(tmp_path):
    capture = tmp_path / "capture_intake"
    for folder_name, tag in (("3 BANGLE 22", "BG22_1"), ("8 BANGLE 22", "BG22_2")):
        folder = capture / folder_name
        folder.mkdir(parents=True)
        (folder / f"{tag}.jpg").write_bytes(b"x")

    rows = category_dashboard.category_breakdown(str(capture), "does-not-exist")
    row = next(r for r in rows if r["label"] == "BANGLE 22")

    assert row["captured"] == 2
    assert row["folders"] == ["3 BANGLE 22", "8 BANGLE 22"]
    assert row["folder"] == "8 BANGLE 22"


def test_counts_processed_images_by_category_label(tmp_path):
    processed = tmp_path / "processed"
    variety = processed / "TOPS 22"
    variety.mkdir(parents=True)
    (variety / "TP22_1.jpg").write_bytes(b"x")
    (variety / "TP22_2.jpg").write_bytes(b"x")

    rows = category_dashboard.category_breakdown("does-not-exist", str(processed))
    row = next(r for r in rows if r["label"] == "TOPS 22")

    assert row["processed"] == 2
    assert row["captured"] == 2


def test_coverage_keeps_approved_items_after_raw_moves_to_processed(tmp_path):
    processed = tmp_path / "processed" / "BANGLE 22"
    processed.mkdir(parents=True)
    (processed / "BG22_1.jpg").write_bytes(b"x")
    (processed / "BG22_2.jpg").write_bytes(b"x")

    rows = category_dashboard.category_breakdown(
        str(tmp_path / "capture_intake"),
        str(tmp_path / "processed"),
        stock_labels=("BG22/1", "BG22/2", "BG22/3", "BG22/4"),
    )
    row = next(r for r in rows if r["label"] == "BANGLE 22")

    assert row["captured"] == 2
    assert row["processed"] == 2
    assert round(row["captured"] / row["stock_total"] * 100) == 50


def test_category_with_no_folder_yet_reports_zero_not_an_error(tmp_path):
    capture = tmp_path / "capture_intake"
    capture.mkdir()

    rows = category_dashboard.category_breakdown(str(capture), str(tmp_path / "processed"))

    assert all(r["captured"] == 0 and r["processed"] == 0 for r in rows)


def test_current_stock_labels_supply_per_category_denominators():
    rows = category_dashboard.category_breakdown(
        "does-not-exist",
        "does-not-exist-either",
        stock_labels=("LR22/1", "LR22/2", "TP22/1"),
    )

    ladies_ring = next(row for row in rows if row["key"] == "ladies_ring_22")
    tops = next(row for row in rows if row["key"] == "tops_22")
    assert ladies_ring["stock_total"] == 2
    assert tops["stock_total"] == 1
    assert sum(row["stock_total"] for row in rows) == 3


def test_review_verdicts_supply_approved_and_rejected_counts():
    rows = category_dashboard.category_breakdown(
        "missing",
        "missing",
        review_state={
            "GR22_1": {"verdict": "approved"},
            "GR22_2": {"verdict": "rejected"},
            "GR22_3": {"verdict": "pending"},
        },
    )
    row = next(r for r in rows if r["label"] == "GENTS RING 22")
    assert row["approved"] == 1
    assert row["rejected"] == 1


def test_uploaded_server_images_are_counted_by_category(tmp_path):
    uploaded = tmp_path / "server" / "BANGLE 22"
    uploaded.mkdir(parents=True)
    (uploaded / "BG22_1.png").write_bytes(b"x")
    (uploaded / "BG22_1.Jpg").write_bytes(b"x")
    (uploaded / "BG22_2.png").write_bytes(b"x")

    rows = category_dashboard.category_breakdown(
        "missing",
        "missing",
        uploaded_root=tmp_path / "server",
    )
    row = next(r for r in rows if r["label"] == "BANGLE 22")

    assert row["uploaded"] == 2
