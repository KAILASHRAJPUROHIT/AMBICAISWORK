"""Stock cache and schedule tests."""

import os
import sys
from datetime import date, datetime, timezone


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import stock_catalog
import stock_excel


def test_next_scan_is_11_daily_and_thursday_has_second_scan():
    assert stock_catalog.next_scheduled_scan(
        datetime(2026, 7, 29, 15, 0)
    ) == datetime(2026, 7, 30, 11, 0)
    assert stock_catalog.next_scheduled_scan(
        datetime(2026, 7, 30, 11, 1)
    ) == datetime(2026, 7, 30, 13, 0)
    assert stock_catalog.next_scheduled_scan(
        datetime(2026, 7, 30, 13, 1)
    ) == datetime(2026, 7, 31, 11, 0)


def test_next_scan_preserves_timezone():
    after = datetime(2026, 7, 30, 11, 1, tzinfo=timezone.utc)
    assert stock_catalog.next_scheduled_scan(after) == datetime(
        2026, 7, 30, 13, 0, tzinfo=timezone.utc
    )


def test_cache_loads_real_workbook_once(monkeypatch):
    cache = stock_catalog.StockCatalogCache(
        os.path.join(stock_excel.BASE, "Stock")
    )
    calls = 0
    original = stock_excel.load_stock_workbook

    def counted_load(path):
        nonlocal calls
        calls += 1
        return original(path)

    monkeypatch.setattr(stock_excel, "load_stock_workbook", counted_load)

    first = cache.refresh(as_of=date(2026, 7, 31))
    second = cache.refresh(as_of=date(2026, 7, 31))

    assert first.reloaded is True
    assert second.reloaded is False
    assert calls == 1
    assert cache.lookup("bb22/1").variety_name == "PLAIN"
    assert cache.lookup("BB22_1").variety_name == "PLAIN"
    assert cache.lookup("not-a-real-tag") is None


def test_cache_counts_compact_latest_and_routes_from_previous_rich_workbook():
    cache = stock_catalog.StockCatalogCache(
        os.path.join(stock_excel.BASE, "Stock")
    )

    result = cache.refresh(as_of=date(2026, 8, 1))

    assert result.inventory.record_count == 2814
    assert result.snapshot.source_path.name == "31072026.xls"
    assert result.warning is not None
    assert "39 current tag(s)" in result.warning
    assert cache.inventory_tag_count == 2814
    assert cache.lookup("BB22_1") is not None
