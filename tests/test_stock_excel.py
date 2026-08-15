"""Tests for read-only dated stock-workbook ingestion."""

import os
import sys
from datetime import date, time
from pathlib import Path

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


def _rows(*data_rows):
    return [
        ["Aradhana Jewellers"],
        ["Label/Tags Closing Stock Report As On Date : 30/07/2026"],
        HEADERS,
        *data_rows,
    ]


def test_filename_date_and_discovery_use_ddmmyyyy(tmp_path):
    (tmp_path / "01082026.xls").write_bytes(b"")
    (tmp_path / "31072026.xls").write_bytes(b"")
    (tmp_path / "not-a-stock-file.xls").write_bytes(b"")
    (tmp_path / "~$01082026.xls").write_bytes(b"")

    discovered = stock_excel.discover_stock_workbooks(tmp_path)

    assert [path.name for path in discovered] == [
        "31072026.xls",
        "01082026.xls",
    ]
    assert stock_excel.stock_date_from_filename(discovered[0]) == date(2026, 7, 31)
    assert stock_excel.latest_stock_workbook(tmp_path).name == "01082026.xls"
    assert (
        stock_excel.latest_stock_workbook(tmp_path, as_of=date(2026, 7, 31)).name
        == "31072026.xls"
    )


def test_latest_workbook_fails_on_same_day_ambiguity(tmp_path):
    (tmp_path / "31072026.xls").write_bytes(b"")
    (tmp_path / "31072026.xlsx").write_bytes(b"")

    with pytest.raises(stock_excel.StockWorkbookError, match="Multiple"):
        stock_excel.latest_stock_workbook(tmp_path)


def test_parse_rows_preserves_blank_variety_and_report_date():
    rows = _rows(
        ["TP22/1", "TP1", "TP22", "22 KT", "CASTING", 2.5, 2.4, 1, "ABC123"],
        ["GC1/1", "GC1", "GC1", "24 KT", "", 1, 1, 2, ""],
        ["", "", "", "", "", 3.5, 3.4, 3, ""],
    )

    snapshot = stock_excel._parse_sheet(
        Path("31072026.xls"),
        "Sheet",
        rows,
    )

    assert snapshot.filename_date == date(2026, 7, 31)
    assert snapshot.report_date == date(2026, 7, 30)
    assert snapshot.record_count == 2
    assert snapshot.total_pieces == 3
    assert snapshot.varieties == ("CASTING",)
    assert snapshot.blank_variety_labels == ("GC1/1",)
    assert snapshot.records[0].huids == ("ABC123",)
    assert snapshot.records[0].routing_key("tops") == ("tops", "CASTING")
    assert snapshot.records[1].routing_key("gold_coin") == (
        "gold_coin",
        stock_excel.GENERAL_VARIETY,
    )
    assert snapshot.lookup_label("TP22_1").label_no == "TP22/1"
    assert snapshot.lookup_label("tp22/1").label_no == "TP22/1"


def test_duplicate_labels_fail_case_insensitively():
    rows = _rows(
        ["TP22/1", "TP1", "TP22", "22 KT", "CASTING", 2.5, 2.4, 1, ""],
        ["tp22/1", "TP2", "TP22", "22 KT", "PLAIN", 3.5, 3.4, 1, ""],
    )

    with pytest.raises(stock_excel.StockDataError, match="Duplicate Label No"):
        stock_excel._parse_sheet(Path("31072026.xls"), "Sheet", rows)


def test_capture_safe_label_collision_fails_loudly():
    rows = _rows(
        ["TP22/1", "TP1", "TP22", "22 KT", "CASTING", 2.5, 2.4, 1, ""],
        ["TP22_1", "TP2", "TP22", "22 KT", "PLAIN", 3.5, 3.4, 1, ""],
    )
    snapshot = stock_excel._parse_sheet(Path("31072026.xls"), "Sheet", rows)

    with pytest.raises(stock_excel.StockDataError, match="both map"):
        snapshot.records_by_filename_label()


def test_missing_required_header_fails_loudly():
    rows = [["Label No", "Variety Name"], ["TP22/1", "CASTING"]]

    with pytest.raises(stock_excel.StockSchemaError, match="required columns"):
        stock_excel._parse_sheet(Path("31072026.xls"), "Sheet", rows)


def test_minimal_inventory_accepts_compact_daily_export(monkeypatch, tmp_path):
    workbook = tmp_path / "01082026.xls"
    workbook.write_bytes(b"placeholder")
    monkeypatch.setattr(
        stock_excel,
        "_read_xls",
        lambda _path: [("Sheet", [["ItemName", "Label No"], ["TOPS 22", "TP22/1"]])],
    )

    inventory = stock_excel.load_stock_label_inventory(workbook)

    assert inventory.record_count == 1
    assert inventory.labels == ("TP22/1",)


def test_schedule_is_11_daily_and_13_additionally_on_thursday():
    assert stock_excel.scheduled_scan_times(date(2026, 7, 31)) == (time(11),)
    assert stock_excel.scheduled_scan_times(date(2026, 7, 30)) == (
        time(11),
        time(13),
    )


def test_real_31072026_workbook_schema_and_totals_are_stable():
    workbook = Path(stock_excel.BASE) / "Stock" / "31072026.xls"
    before = workbook.stat()

    snapshot = stock_excel.load_stock_workbook(workbook)

    after = workbook.stat()
    assert snapshot.sheet_name == "Sheet"
    assert snapshot.filename_date == date(2026, 7, 31)
    assert snapshot.report_date == date(2026, 7, 30)
    assert snapshot.record_count == 2795
    assert snapshot.total_pieces == 2898
    assert snapshot.source_total_pieces == 2898
    assert len(snapshot.varieties) == 184
    assert len(snapshot.blank_variety_labels) == 72
    assert snapshot.records[0].label_no == "BB22/1"
    assert snapshot.records_by_label()["bb22/1"].variety_name == "PLAIN"
    assert (after.st_size, after.st_mtime_ns) == (
        before.st_size,
        before.st_mtime_ns,
    )
