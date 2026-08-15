"""Read-only dashboard metric tests."""

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import dashboard_stats
import stock_excel


HEADERS = [
    "Label No",
    "Old BarcodeNo",
    "Prefix",
    "Carat",
    "Variety Name",
    "Gross Wt",
    "Net Wt",
    "Pcs",
    "HUID",
]


def _write_image(root, relative, timestamp):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"image")
    os.utime(path, (timestamp, timestamp))
    return path


def _stock_snapshot():
    return stock_excel._parse_sheet(
        Path("31072026.xls"),
        "Sheet",
        [
            ["As On Date : 30/07/2026"],
            HEADERS,
            ["TP22/1", "TP1", "TP22", "22 KT", "CASTING", 1, 1, 2, ""],
            ["", "", "", "", "", 1, 1, 2, ""],
        ],
    )


def test_dashboard_counts_primary_images_and_excludes_tag_archive(tmp_path):
    roots = {
        name: tmp_path / name
        for name in (
            "capture",
            "processing",
            "processed",
            "needs_review",
            "rejected",
        )
    }
    for root in roots.values():
        root.mkdir()

    today = datetime(2026, 7, 31, 9, 0, tzinfo=timezone.utc)
    today_timestamp = today.timestamp()
    yesterday_timestamp = datetime(
        2026, 7, 30, 9, 0, tzinfo=timezone.utc
    ).timestamp()
    latest_capture = _write_image(
        roots["capture"], "Tops 1/TP22_1.jpg", today_timestamp
    )
    _write_image(
        roots["capture"], "Tops 1/TP22_2.jpg", yesterday_timestamp
    )
    _write_image(
        roots["capture"],
        "Tops 1/_tag_archive/TP22_1_tag.jpg",
        today_timestamp,
    )
    _write_image(
        roots["processing"], "Tops 1/TP22_1.jpg", today_timestamp
    )
    latest_processed = _write_image(
        roots["processed"], "Tops 1/TP22_0.jpg", yesterday_timestamp
    )
    _write_image(
        roots["needs_review"], "Tops 1/TP22_3.jpg", today_timestamp
    )
    _write_image(
        roots["rejected"], "Tops 1/TP22_4.jpg", today_timestamp
    )

    stats = dashboard_stats.collect_dashboard_stats(
        capture_root=roots["capture"],
        processing_root=roots["processing"],
        processed_root=roots["processed"],
        needs_review_root=roots["needs_review"],
        rejected_root=roots["rejected"],
        stock_snapshot=_stock_snapshot(),
        now=today,
        timezone=timezone.utc,
        external_health={"engines": {"ok": True, "detail": "available"}},
    )

    assert stats.captured_today == 1
    assert stats.captured_total == 2
    assert stats.stock_tags == 1
    assert stats.stock_pieces == 2
    assert stats.processing_available == 1
    assert stats.processed_total == 1
    assert stats.needs_review_total == 1
    assert stats.rejected_total == 1
    assert stats.last_captured_at == datetime.fromtimestamp(
        latest_capture.stat().st_mtime, tz=timezone.utc
    )
    assert stats.last_processed_at == datetime.fromtimestamp(
        latest_processed.stat().st_mtime, tz=timezone.utc
    )
    assert stats.overall_ok is True
    assert stats.as_dict()["health"]["engines"]["ok"] is True


def test_missing_roots_and_stock_are_reported_unhealthy(tmp_path):
    stats = dashboard_stats.collect_dashboard_stats(
        capture_root=tmp_path / "capture",
        processing_root=tmp_path / "processing",
        processed_root=tmp_path / "processed",
        needs_review_root=tmp_path / "needs_review",
        rejected_root=tmp_path / "rejected",
        stock_snapshot=None,
        now=datetime(2026, 7, 31),
    )

    assert stats.overall_ok is False
    assert stats.stock_tags == 0
    assert stats.health["capture"].ok is False
    assert stats.health["stock"].ok is False

