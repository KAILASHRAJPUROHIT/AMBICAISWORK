"""check_master_stock() cross-references a scanned tag code against the
daily Ornate stock Excel drop (Stock/DDMMYYYY.xls). Two different export
schemas have been observed in practice (confirmed with the user 2026-08-02
on real files: a reduced ItemName+LabelNo export on one day, a full
9-column export with weights/HUID on another) — these tests lock in that
the parser handles both without the caller needing to know which one it got.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import xlrd

import capture_tool as ct


def _write_xls_like(monkeypatch, rows):
    """Patches xlrd.open_workbook to serve `rows` (a list of lists), bypassing
    the need for a real .xls file. The parser reads via xlrd rather than pandas
    because the service interpreter has xlrd but no pandas -- see
    _parse_master_stock. Rows are padded to equal width, as a real sheet is."""
    width = max((len(r) for r in rows), default=0)
    padded = [list(r) + [""] * (width - len(r)) for r in rows]

    class _Sheet:
        nrows = len(padded)

        def row_values(self, index):
            return padded[index]

    class _Book:
        def sheet_by_index(self, index):
            return _Sheet()

    monkeypatch.setattr(xlrd, "open_workbook", lambda path: _Book())


def test_parses_reduced_schema(monkeypatch):
    rows = [
        ["Aradhana Jewellers"],
        ["Label/Tags Closing Stock Report (BAJU BANDH 22) As On Date : 01/08/2026"],
        ["ItemName", "Label No"],
        ["BAJU BANDH 22", "BB22/1"],
        ["BAJU BANDH 22", "BB22/2"],
    ]
    _write_xls_like(monkeypatch, rows)
    labels = ct._parse_master_stock("fake.xls")
    assert labels["BB22/1"]["item_name"] == "BAJU BANDH 22"
    assert labels["BB22/2"]["item_name"] == "BAJU BANDH 22"
    assert labels["BB22/1"]["gross_wt"] is None


def test_parses_full_schema(monkeypatch):
    rows = [
        ["Aradhana Jewellers"],
        ["Label/Tags Closing Stock Report (BABY BRACLET 22) As On Date : 31/07/2026"],
        ["Label No", "Old BarcodeNo", "Prefix", "Carat", "Variety Name",
         "Gross Wt", "Net Wt", "Pcs", "HUID"],
        ["BB22/1", "BB1", "BB22", "22 KT", "PLAIN", 10.63, 10.63, 1, "TC3XRM"],
        [None, None, None, None, None, 20860.6, 20252.1, 2898, None],  # totals row
    ]
    _write_xls_like(monkeypatch, rows)
    labels = ct._parse_master_stock("fake.xls")
    # item_name comes from the TAG CODE's prefix, not the section title.
    # BB22 is BAJU BANDH 22; BABY BRACLET 22 is BV22. The real full-schema
    # export carries a single section title followed by every category's rows
    # in one block, so trusting the title mislabelled 2785 of 2795 items
    # (fixed 2026-09-01) -- this fixture reproduces exactly that mismatch.
    assert labels["BB22/1"] == {
        "item_name": "BAJU BANDH 22", "old_barcode": "BB1", "prefix": "BB22",
        "carat": "22 KT", "variety": "PLAIN", "gross_wt": 10.63, "net_wt": 10.63,
        "pcs": 1, "huid": "TC3XRM",
    }
    assert len(labels) == 1, "the blank-label totals row must not be parsed as a stock item"


def test_multiple_category_sections_in_one_sheet(monkeypatch):
    rows = [
        ["Label/Tags Closing Stock Report (BAJU BANDH 22) As On Date : 01/08/2026"],
        ["ItemName", "Label No"],
        ["BAJU BANDH 22", "BB22/1"],
        ["Label/Tags Closing Stock Report (BANGLE 22) As On Date : 01/08/2026"],
        ["ItemName", "Label No"],
        ["BANGLE 22", "BG22/1"],
    ]
    _write_xls_like(monkeypatch, rows)
    labels = ct._parse_master_stock("fake.xls")
    assert labels["BB22/1"]["item_name"] == "BAJU BANDH 22"
    assert labels["BG22/1"]["item_name"] == "BANGLE 22"


def test_check_master_stock_unknown_code_fails_open(monkeypatch):
    monkeypatch.setattr(ct, "_load_master_stock_labels", lambda: {})
    result = ct.check_master_stock("NOPE/1")
    assert result == {"known": False, "row": None}


def test_check_master_stock_read_error_fails_open(monkeypatch):
    def boom():
        raise RuntimeError("Stock folder unreachable")
    monkeypatch.setattr(ct, "_load_master_stock_labels", boom)
    result = ct.check_master_stock("BB22/1")
    assert result == {"known": False, "row": None}


def test_latest_stock_file_picks_newest_by_filename_date(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "MASTER_STOCK_DIR", str(tmp_path))
    (tmp_path / "31072026.xls").write_bytes(b"old")
    (tmp_path / "01082026.xls").write_bytes(b"new")
    assert ct._latest_stock_file() == str(tmp_path / "01082026.xls")
