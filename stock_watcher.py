"""Persistent, fail-closed watcher for dated daily stock workbooks."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import stock_excel
import stock_reconciliation


BASE = Path(__file__).resolve().parent
STATUS_PATH = BASE / "config" / "stock_watcher_status.json"


def _atomic_status(payload: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, STATUS_PATH)


def read_status() -> dict:
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return {}


def current_workbook(stock_dir: str | os.PathLike[str] = stock_excel.STOCK_DIR) -> Path:
    """Return the last fully validated workbook, or validate through normal discovery."""

    status = read_status()
    candidate = Path(str(status.get("active_workbook") or ""))
    if candidate.is_file() and candidate.parent.resolve() == Path(stock_dir).resolve():
        return candidate
    return stock_excel.latest_stock_workbook(stock_dir)


class StockFolderWatcher:
    def __init__(self, stock_dir: str | os.PathLike[str] = stock_excel.STOCK_DIR, stable_scans: int = 2):
        self.stock_dir = Path(stock_dir)
        self.stable_scans = max(2, int(stable_scans))
        self._signature: tuple[str, int, int] | None = None
        self._stable_count = 0
        self._validated_signature: tuple[str, int, int] | None = None

    def scan_once(self) -> dict:
        latest = stock_excel.latest_stock_workbook(self.stock_dir)
        stat = latest.stat()
        signature = (str(latest.resolve()), stat.st_size, stat.st_mtime_ns)
        if signature == self._signature:
            self._stable_count += 1
        else:
            self._signature = signature
            self._stable_count = 1

        existing = read_status()
        if signature == self._validated_signature:
            return existing
        if self._stable_count < self.stable_scans:
            payload = {
                **existing,
                "state": "waiting_for_copy_to_finish",
                "observed_workbook": str(latest.resolve()),
                "observed_size": stat.st_size,
                "stable_scans": self._stable_count,
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_status(payload)
            return payload

        try:
            categories = stock_excel.load_stock_label_categories(latest)
            inventory = stock_excel.load_stock_label_inventory(latest)
        except Exception as exc:
            payload = {
                **existing,
                "state": "rejected_new_workbook",
                "observed_workbook": str(latest.resolve()),
                "error": f"{type(exc).__name__}: {exc}",
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_status(payload)
            self._validated_signature = signature
            return payload

        previous_active = Path(str(existing.get("active_workbook") or ""))
        reconciliation = None
        if previous_active.is_file() and previous_active.resolve() != latest.resolve():
            try:
                pair_previous, pair_current = stock_reconciliation._candidate_pair(self.stock_dir)
                if pair_previous.resolve() != previous_active.resolve() or pair_current.resolve() != latest.resolve():
                    raise stock_reconciliation.StockReconciliationError(
                        "Newest workbook cannot be compared directly with the active workbook"
                    )
                reconciliation = stock_reconciliation.ensure_reconciled(stock_dir=self.stock_dir)
            except Exception as exc:
                payload = {
                    **existing,
                    "state": "reconciliation_blocked",
                    "observed_workbook": str(latest.resolve()),
                    "error": f"{type(exc).__name__}: {exc}",
                    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                }
                _atomic_status(payload)
                return payload

        payload = {
            "state": "active",
            "active_workbook": str(latest.resolve()),
            "workbook_date": stock_excel.stock_date_from_filename(latest).isoformat(),
            "tag_count": inventory.record_count,
            "category_lookup_count": len(categories),
            "size": stat.st_size,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        if reconciliation is not None:
            payload["transition"] = {
                "signature": reconciliation.signature,
                "previous_workbook": reconciliation.previous_workbook,
                "current_workbook": reconciliation.current_workbook,
                "sold_count": len(reconciliation.sold_tags),
                "added_count": len(reconciliation.new_tags),
                "moved_files": reconciliation.moved_files,
                "sold_tags": list(reconciliation.sold_tags),
                "added_tags": list(reconciliation.new_tags),
            }
        _atomic_status(payload)
        self._validated_signature = signature
        return payload

    def run_forever(self, interval_seconds: float = 2.0) -> None:
        while True:
            try:
                self.scan_once()
            except Exception as exc:
                existing = read_status()
                _atomic_status({
                    **existing,
                    "state": "watcher_error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                })
            time.sleep(max(1.0, interval_seconds))


def start_daemon(stock_dir: str | os.PathLike[str] = stock_excel.STOCK_DIR) -> threading.Thread:
    watcher = StockFolderWatcher(stock_dir)
    thread = threading.Thread(
        target=watcher.run_forever,
        name="stock-folder-watcher",
        daemon=True,
    )
    thread.start()
    return thread
