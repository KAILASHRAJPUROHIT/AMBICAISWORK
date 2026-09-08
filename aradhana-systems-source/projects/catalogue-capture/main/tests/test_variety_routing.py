"""
variety_routing.resolve() must be impossible to fail loudly from — it feeds
an opt-in override into a LIVE, already-working pipeline (autonomous_loop's
per-pair bg/model cycling), so any failure mode here has to degrade to "use
the caller's existing selection", never a stalled or failed pair.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import item_routing
import stock_excel
import variety_routing


def _record(*, label_no="LC22/13", variety="ANTIQUE"):
    return stock_excel.StockRecord(
        label_no=label_no,
        old_barcode_no="",
        prefix="LC",
        carat="22",
        variety_name=variety,
        gross_weight=Decimal("3.0"),
        net_weight=Decimal("2.8"),
        pieces=1,
        huids=(),
        source_row=2,
    )


class _FakeStock:
    """Stands in for stock_catalog.StockCatalogCache without touching disk."""

    def __init__(self, record=None, *, refresh_raises=False):
        self._record = record
        self._refresh_raises = refresh_raises

    def refresh(self):
        if self._refresh_raises:
            raise stock_excel.StockWorkbookError("workbook unreadable")

    def lookup(self, label_no):
        if self._record is not None and label_no in (
            self._record.label_no,
            stock_excel.safe_filename_label(self._record.label_no),
        ):
            return self._record
        return None


class _FakeRouter:
    def __init__(self, decision=None, *, raises=None):
        self._decision = decision
        self._raises = raises

    def route(self, record, ornament_type, *, manual_override=None):
        if self._raises:
            raise self._raises
        return self._decision


def _decision(background_path="C:/bg.jpg", model_candidates=("C:/model.jpg",), variety="ANTIQUE"):
    return item_routing.RoutingDecision(
        tag_code="LC22/13",
        ornament_type="locket",
        variety=variety,
        output_bucket=variety,
        studio_output="C:/out/LC22_13.jpg",
        model_output="C:/out/LC22_13_2.jpg",
        background_theme="Regular",
        background_path=background_path,
        model_theme="",
        model_group="female",
        model_pose="neck",
        model_candidates=tuple(model_candidates) if model_candidates else (),
        model_image=None,
        manually_overridden=False,
    )


def test_resolves_a_known_tag_to_real_paths():
    record = _record()
    stock = _FakeStock(record)
    router = _FakeRouter(_decision())

    result = variety_routing.resolve("LC22_13", "locket", stock=stock, router=router)

    assert result is not None
    assert result.background_path == "C:/bg.jpg"
    assert result.model_path == "C:/model.jpg"
    assert result.variety == "ANTIQUE"


def test_unknown_tag_returns_none_not_an_error():
    stock = _FakeStock(record=None)
    router = _FakeRouter(_decision())

    assert variety_routing.resolve("NOPE22_1", "locket", stock=stock, router=router) is None


@pytest.mark.parametrize("label", ["", None])
def test_blank_inputs_return_none(label):
    stock = _FakeStock(_record())
    router = _FakeRouter(_decision())
    assert variety_routing.resolve(label, "locket", stock=stock, router=router) is None
    assert variety_routing.resolve("LC22_13", label, stock=stock, router=router) is None


def test_stock_refresh_failure_returns_none_not_raises():
    stock = _FakeStock(_record(), refresh_raises=True)
    router = _FakeRouter(_decision())

    assert variety_routing.resolve("LC22_13", "locket", stock=stock, router=router) is None


def test_routing_error_returns_none_not_raises():
    stock = _FakeStock(_record())
    router = _FakeRouter(raises=item_routing.RoutingError("no background asset"))

    assert variety_routing.resolve("LC22_13", "locket", stock=stock, router=router) is None


def test_unexpected_exception_returns_none_not_raises():
    """Never let a routing fault stall or fail a real pair — this is the
    entire reason this module exists rather than callers using ItemRouter
    directly."""
    stock = _FakeStock(_record())
    router = _FakeRouter(raises=RuntimeError("boom"))

    assert variety_routing.resolve("LC22_13", "locket", stock=stock, router=router) is None


def test_no_model_candidates_returns_none():
    stock = _FakeStock(_record())
    router = _FakeRouter(_decision(model_candidates=()))

    assert variety_routing.resolve("LC22_13", "locket", stock=stock, router=router) is None


def test_lookup_matches_capture_safe_filename_form():
    """The real caller passes a filename stem (e.g. 'LC22_13'), not the
    slash-form stock tag ('LC22/13') — this is what makes that work."""
    record = _record(label_no="LC22/13")
    stock = _FakeStock(record)
    router = _FakeRouter(_decision())

    result = variety_routing.resolve("LC22_13", "locket", stock=stock, router=router)
    assert result is not None


def test_shared_instances_are_lazily_built_and_resettable():
    variety_routing.reset_for_tests()
    assert variety_routing._stock is None
    assert variety_routing._router is None
