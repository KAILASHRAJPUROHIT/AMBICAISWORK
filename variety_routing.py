"""Opt-in, fail-safe variety-based asset resolution shared by Auto and Manual.

Wraps ``item_routing.ItemRouter`` (see its module docstring for the exact
precedence and folder-layout rules) with a stock-tag lookup, for callers that
need real filesystem paths for an engine call rather than the JSON-safe
relative paths ``routing_preview`` returns for the API layer.

This module is deliberately impossible to fail loudly from: any problem —
unknown tag, an unreadable/missing stock workbook, no compatible asset on
disk for this ornament+variety — returns ``None`` rather than raising. That
is what makes this safe to flip on for a live pipeline: a tag with no stock
match costs nothing more than "the caller's existing selection happens
instead", never a stalled or failed pair. Callers MUST keep their own
existing background/model selection as the fallback when this returns None.
"""

from __future__ import annotations

from dataclasses import dataclass

import item_routing
import stock_catalog


_stock: stock_catalog.StockCatalogCache | None = None
_router: item_routing.ItemRouter | None = None


def _get_stock() -> stock_catalog.StockCatalogCache:
    global _stock
    if _stock is None:
        _stock = stock_catalog.StockCatalogCache()
    return _stock


def _get_router() -> item_routing.ItemRouter:
    global _router
    if _router is None:
        _router = item_routing.ItemRouter.from_configured_manifest()
    return _router


def reset_for_tests() -> None:
    """Drop the lazily-built singletons so tests can inject fresh instances."""
    global _stock, _router
    _stock = None
    _router = None


@dataclass(frozen=True, slots=True)
class VarietyAssets:
    background_path: str
    model_path: str
    variety: str


def resolve(
    tag_label: str,
    ornament_type: str,
    *,
    stock: stock_catalog.StockCatalogCache | None = None,
    router: item_routing.ItemRouter | None = None,
) -> VarietyAssets | None:
    """Best-effort variety-based asset resolution. Never raises.

    ``stock``/``router`` are accepted for tests; production callers should
    omit both and use the shared lazily-built instances.
    """

    if not tag_label or not ornament_type:
        return None

    stock_cache = stock or _get_stock()
    try:
        stock_cache.refresh()
    except Exception:
        return None

    record = stock_cache.lookup(tag_label)
    if record is None:
        return None

    try:
        decision = (router or _get_router()).route(record, ornament_type)
    except item_routing.RoutingError:
        return None
    except Exception:
        return None

    if not decision.model_candidates:
        return None

    return VarietyAssets(
        background_path=str(decision.background_path),
        model_path=str(decision.model_candidates[0]),
        variety=decision.variety,
    )
