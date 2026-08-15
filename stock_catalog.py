"""Thread-safe in-memory cache and schedule helpers for stock workbooks."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import stock_excel


@dataclass(frozen=True, slots=True)
class StockRefreshResult:
    snapshot: stock_excel.StockSnapshot
    reloaded: bool
    inventory: stock_excel.StockLabelInventory
    warning: str | None = None


class StockCatalogCache:
    """Keep the last successfully validated stock workbook available.

    A broken or partially-written newer workbook raises to the caller without
    replacing the last good snapshot.
    """

    def __init__(self, stock_dir: str | Path = stock_excel.STOCK_DIR):
        self.stock_dir = Path(stock_dir)
        self._lock = threading.RLock()
        self._snapshot: stock_excel.StockSnapshot | None = None
        self._inventory: stock_excel.StockLabelInventory | None = None
        self._signature: tuple[tuple[str, int, int], tuple[str, int, int]] | None = None
        self._warning: str | None = None

    @property
    def snapshot(self) -> stock_excel.StockSnapshot | None:
        with self._lock:
            return self._snapshot

    @property
    def inventory(self) -> stock_excel.StockLabelInventory | None:
        with self._lock:
            return self._inventory

    @property
    def inventory_tag_count(self) -> int | None:
        inventory = self.inventory
        return inventory.record_count if inventory is not None else None

    def refresh(self, *, as_of: date | None = None) -> StockRefreshResult:
        source = stock_excel.latest_stock_workbook(self.stock_dir, as_of=as_of)
        inventory = stock_excel.load_stock_label_inventory(source)
        source_stat = source.stat()
        inventory_signature = (
            str(source.resolve()),
            source_stat.st_size,
            source_stat.st_mtime_ns,
        )
        with self._lock:
            if (
                self._snapshot is not None
                and self._inventory is not None
                and self._signature is not None
                and self._signature[0] == inventory_signature
            ):
                routing_path = Path(self._signature[1][0])
                if routing_path.is_file():
                    routing_stat = routing_path.stat()
                    current_routing_signature = (
                        str(routing_path.resolve()),
                        routing_stat.st_size,
                        routing_stat.st_mtime_ns,
                    )
                    if current_routing_signature == self._signature[1]:
                        return StockRefreshResult(
                            self._snapshot,
                            reloaded=False,
                            inventory=self._inventory,
                            warning=self._warning,
                        )

        routing_snapshot = None
        routing_source = None
        latest_schema_error: stock_excel.StockSchemaError | None = None
        candidates = [
            path
            for path in stock_excel.discover_stock_workbooks(self.stock_dir)
            if as_of is None or stock_excel.stock_date_from_filename(path) <= as_of
        ]
        for candidate in reversed(candidates):
            try:
                routing_snapshot = stock_excel.load_stock_workbook(candidate)
                routing_source = candidate
                break
            except stock_excel.StockSchemaError as exc:
                if candidate == source:
                    latest_schema_error = exc
        if routing_snapshot is None or routing_source is None:
            if latest_schema_error is not None:
                raise latest_schema_error
            raise stock_excel.StockSchemaError("No rich stock workbook is available")

        routing_stat = routing_source.stat()
        routing_signature = (
            str(routing_source.resolve()),
            routing_stat.st_size,
            routing_stat.st_mtime_ns,
        )
        signature = (inventory_signature, routing_signature)
        routing_labels = set(routing_snapshot.records_by_label())
        missing_routing = sum(
            label.casefold() not in routing_labels for label in inventory.labels
        )
        warning = None
        if routing_source != source:
            warning = (
                f"{inventory.record_count} current tags from {source.name}; "
                f"routing metadata from {routing_source.name}; "
                f"{missing_routing} current tag(s) await rich metadata"
            )
        with self._lock:
            if self._snapshot is not None and signature == self._signature:
                return StockRefreshResult(
                    self._snapshot,
                    reloaded=False,
                    inventory=self._inventory or inventory,
                    warning=warning,
                )

        with self._lock:
            self._snapshot = routing_snapshot
            self._inventory = inventory
            self._signature = signature
            self._warning = warning
            return StockRefreshResult(
                routing_snapshot,
                reloaded=True,
                inventory=inventory,
                warning=warning,
            )

    def lookup(self, label_no: str) -> stock_excel.StockRecord | None:
        with self._lock:
            snapshot = self._snapshot
        if snapshot is None:
            return None
        return snapshot.lookup_label(label_no)


def next_scheduled_scan(after: datetime) -> datetime:
    """Return the next local 11:00 scan or additional Thursday 13:00 scan."""

    for offset in range(8):
        day = after.date() + timedelta(days=offset)
        for scan_time in stock_excel.scheduled_scan_times(day):
            candidate = datetime.combine(day, scan_time, tzinfo=after.tzinfo)
            if candidate > after:
                return candidate
    raise RuntimeError("Could not calculate the next stock scan")
