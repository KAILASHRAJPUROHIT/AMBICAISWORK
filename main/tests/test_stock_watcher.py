from pathlib import Path

import stock_watcher


class _Inventory:
    record_count = 3


def test_new_workbook_must_be_stable_then_becomes_active(tmp_path, monkeypatch):
    workbook = tmp_path / "11082026.xlsx"
    workbook.write_bytes(b"complete workbook")
    status = tmp_path / "status.json"
    monkeypatch.setattr(stock_watcher, "STATUS_PATH", status)
    monkeypatch.setattr(stock_watcher.stock_excel, "latest_stock_workbook", lambda _root: workbook)
    monkeypatch.setattr(stock_watcher.stock_excel, "load_stock_label_categories", lambda _path: {"a": "TOPS 22"})
    monkeypatch.setattr(stock_watcher.stock_excel, "load_stock_label_inventory", lambda _path: _Inventory())

    watcher = stock_watcher.StockFolderWatcher(tmp_path)
    assert watcher.scan_once()["state"] == "waiting_for_copy_to_finish"
    activated = watcher.scan_once()
    assert activated["state"] == "active"
    assert activated["active_workbook"] == str(workbook.resolve())
    assert stock_watcher.current_workbook(tmp_path) == workbook


def test_new_workbook_reconciles_before_activation(tmp_path, monkeypatch):
    old = tmp_path / "10082026.xls"
    new = tmp_path / "11082026.xls"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    status = tmp_path / "status.json"
    monkeypatch.setattr(stock_watcher, "STATUS_PATH", status)
    stock_watcher._atomic_status({"state": "active", "active_workbook": str(old.resolve())})
    monkeypatch.setattr(stock_watcher.stock_excel, "latest_stock_workbook", lambda _root: new)
    monkeypatch.setattr(stock_watcher.stock_excel, "load_stock_label_categories", lambda _path: {"a": "TOPS 22"})
    monkeypatch.setattr(stock_watcher.stock_excel, "load_stock_label_inventory", lambda _path: _Inventory())

    class _Result:
        signature = "delta-1"
        previous_workbook = old.name
        current_workbook = new.name
        sold_tags = ("LR22_1",)
        new_tags = ("JB22_4", "JB22_5")
        moved_files = 3

    monkeypatch.setattr(stock_watcher.stock_reconciliation, "ensure_reconciled", lambda **_kwargs: _Result())
    watcher = stock_watcher.StockFolderWatcher(tmp_path)
    watcher.scan_once()
    activated = watcher.scan_once()
    assert activated["state"] == "active"
    assert activated["transition"]["sold_count"] == 1
    assert activated["transition"]["added_count"] == 2
    assert activated["transition"]["moved_files"] == 3


def test_reconciliation_failure_keeps_previous_active(tmp_path, monkeypatch):
    old = tmp_path / "10082026.xls"
    new = tmp_path / "11082026.xls"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    status = tmp_path / "status.json"
    monkeypatch.setattr(stock_watcher, "STATUS_PATH", status)
    stock_watcher._atomic_status({"state": "active", "active_workbook": str(old.resolve())})
    monkeypatch.setattr(stock_watcher.stock_excel, "latest_stock_workbook", lambda _root: new)
    monkeypatch.setattr(stock_watcher.stock_excel, "load_stock_label_categories", lambda _path: {"a": "TOPS 22"})
    monkeypatch.setattr(stock_watcher.stock_excel, "load_stock_label_inventory", lambda _path: _Inventory())
    monkeypatch.setattr(stock_watcher.stock_reconciliation, "ensure_reconciled", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("safety stop")))
    watcher = stock_watcher.StockFolderWatcher(tmp_path)
    watcher.scan_once()
    blocked = watcher.scan_once()
    assert blocked["state"] == "reconciliation_blocked"
    assert blocked["active_workbook"] == str(old.resolve())


def test_invalid_new_workbook_never_replaces_last_good(tmp_path, monkeypatch):
    old = tmp_path / "10082026.xls"
    new = tmp_path / "11082026.xls"
    old.write_bytes(b"old")
    new.write_bytes(b"broken")
    status = tmp_path / "status.json"
    monkeypatch.setattr(stock_watcher, "STATUS_PATH", status)
    stock_watcher._atomic_status({"state": "active", "active_workbook": str(old.resolve())})
    monkeypatch.setattr(stock_watcher.stock_excel, "latest_stock_workbook", lambda _root: new)
    monkeypatch.setattr(stock_watcher.stock_excel, "load_stock_label_categories", lambda _path: (_ for _ in ()).throw(ValueError("bad workbook")))

    watcher = stock_watcher.StockFolderWatcher(tmp_path)
    watcher.scan_once()
    rejected = watcher.scan_once()
    assert rejected["state"] == "rejected_new_workbook"
    assert rejected["active_workbook"] == str(old.resolve())
    assert stock_watcher.current_workbook(tmp_path) == old
