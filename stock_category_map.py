"""Current stock categories and their exact processing semantics.

``ornament_code_map`` is the single source of truth for the 57 labels in the
current stock workbook.  ``existing_key`` is deliberately the semantic
ornament profile, not the name of a physically compatible background file.
The latter is resolved separately by ``ornament_placement`` so a Jhumka can
reuse an earring stand without being misidentified as a generic earring.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ornament_code_map import CATEGORIES as CURRENT_STOCK_CATEGORIES


@dataclass(frozen=True, slots=True)
class StockCategory:
    key: str            # internal snake_case key, this taxonomy's own
    label: str           # exact spelling from the source sheet/stock data
    existing_key: str | None  # reused internal processing key, or None


CATEGORIES: tuple[StockCategory, ...] = tuple(
    StockCategory(c.key, c.label, c.key)
    for c in CURRENT_STOCK_CATEGORIES
)

assert len(CATEGORIES) == 57, f"expected 57 categories, got {len(CATEGORIES)}"
assert len({c.key for c in CATEGORIES}) == 57, "duplicate key"
assert len({c.label for c in CATEGORIES}) == 57, "duplicate label"

BY_KEY: dict[str, StockCategory] = {c.key: c for c in CATEGORIES}
READY: tuple[StockCategory, ...] = tuple(c for c in CATEGORIES if c.existing_key)
NEEDS_SETUP: tuple[StockCategory, ...] = tuple(c for c in CATEGORIES if not c.existing_key)

# Labels removed from the latest 57-category workbook still exist in older
# capture trays. They remain readable/processable but are intentionally not
# presented as current capture choices or counted in the 57.
_LEGACY: tuple[StockCategory, ...] = (
    StockCategory("chain_18", "CHAIN 18", "chain"),
    StockCategory("earring_18", "EARRING 18", "earrings"),
    StockCategory("gents_bracelet_18", "GENTS BRACELET 18", "gents_bracelet"),
    StockCategory("nath_18", "NATH 18", "nath"),
    StockCategory("tikka_18", "TIKKA 18", "maang_tika"),
)
_LEGACY_BY_KEY = {c.key: c for c in _LEGACY}

assert len(READY) == 57, f"expected 57 ready categories, got {len(READY)}"
assert len(NEEDS_SETUP) == 0, f"expected no blocked categories, got {len(NEEDS_SETUP)}"


def is_ready(key: str) -> bool:
    """True if this category has a real background/model asset and can
    actually generate today."""
    cat = BY_KEY.get(key) or _LEGACY_BY_KEY.get(key)
    return bool(cat and cat.existing_key)


def processing_key(key: str) -> str | None:
    """The existing internal key whose assets this category should reuse,
    or None if nothing exists yet."""
    cat = BY_KEY.get(key) or _LEGACY_BY_KEY.get(key)
    return cat.existing_key if cat else None


# ── folder-name matching (shared with processing_worker.category_from_tray_folder) ──

_TRAY_NUMBER_LEADING = re.compile(r"^\d+\s+")
_TRAY_NUMBER_TRAILING = re.compile(r"\s+\d+$")


def match_label(label: str) -> StockCategory | None:
    """Match an already-normalised (casefolded, tray-number stripped) label
    against CATEGORIES by exact label text. Returns None if no category has
    that label."""
    for cat in CATEGORIES + _LEGACY:
        if cat.label.strip().casefold() == label:
            return cat
    return None


def _label_candidates(folder_name: str) -> list[str]:
    """Both tray-number-stripped forms of a folder name (leading '9 Ladies
    Rings' and trailing 'Ladies Rings 9'), casefolded — mirrors
    processing_worker.category_from_tray_folder's own normalisation so a
    folder recognised there is recognised here too."""
    normalised = " ".join(folder_name.strip().casefold().split())
    return [p.sub("", normalised).strip() for p in (_TRAY_NUMBER_LEADING, _TRAY_NUMBER_TRAILING)]


def category_from_path(path_value: str) -> StockCategory | None:
    """Resolve a category from any folder component in a local/relative path.

    Accepts both current ``<tray> <label>`` folders such as
    ``56 TOPS 22`` and historical ``<label> <tray>`` folders. The nearest
    matching parent wins. A filename by itself does not create a path match.
    """
    if not path_value:
        return None
    parts = [part for part in re.split(r"[/\\]+", str(path_value)) if part]
    for component in reversed(parts[:-1]):
        for label in _label_candidates(component):
            category = match_label(label)
            if category is not None:
                return category
    return None


def captured_keys(*roots: str) -> set[str]:
    """Keys among CATEGORIES for which a real capture-tray folder already
    exists on disk under any of the given roots (e.g. capture_intake, master
    backup) — regardless of whether that category is asset-ready. Used to
    auto-enable a 'needs setup' dropdown entry the moment real capture
    activity for it exists, instead of waiting on a manual code edit to
    ``existing_key``."""
    found: set[str] = set()
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for name in entries:
            if not os.path.isdir(os.path.join(root, name)):
                continue
            for label in _label_candidates(name):
                cat = match_label(label)
                if cat is not None:
                    found.add(cat.key)
                    break
    return found
