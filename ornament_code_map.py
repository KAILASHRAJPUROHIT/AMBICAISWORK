"""
The 57 real stock categories and their ornament-code prefixes, sourced
directly from \\Server2k22\D\01082026.xls (2814 real tags, 2026-08-01) —
each category maps 1:1 to exactly one code prefix (e.g. "BANGLE 22" -> "BG22"),
verified against every real Label No in that report.

Single source of truth for: capture_intake folder naming, auto-category
resolution from a scanned/read tag code, and dashboard per-category counts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Category:
    key: str          # snake_case internal key
    label: str         # exact ItemName from the stock report
    prefix: str        # code prefix, e.g. "BG22"


def _key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")


# (label, prefix) — exact ItemName + prefix pairs verified against the stock report.
_ROWS = (
    ("BABY BRACLET 22", "BV22"),
    ("BABY KADLI 22", "BK22"),
    ("BABY RING 22", "BR22"),
    ("BAJU BANDH 22", "BB22"),
    ("BALI 18", "BL18"),
    ("BALI 22", "BL22"),
    ("BANGLE 22", "BG22"),
    ("CHAIN 22", "CH22"),
    ("DULL 22", "DL22"),
    ("EARRING 22", "ER22"),
    ("FANCY MALA 18", "FM18"),
    ("FANCY MALA 22", "FM22"),
    ("GENTS BRACELET 22", "GB22"),
    ("GENTS KADA 18", "GK18"),
    ("GENTS KADA 22", "GK22"),
    ("GENTS RING 22", "GR22"),
    ("GOLD COIN 22 KT", "GM5"),
    ("Gold Coin 0.025 M", "GM025"),
    ("Gold Coin 0.050 M", "GCM05"),
    ("Gold Coin 0.100 M", "GCM1"),
    ("Gold Coin 0.200 M", "GCM2"),
    ("Gold Coin 0.250 M", "GCM25"),
    ("Gold Coin 0.300 M", "GCM3"),
    ("Gold Coin 0.500 M", "GCM5"),
    ("Gold Coin 0.750 M", "GCM75"),
    ("Gold Coin 1 Gm", "GC1"),
    ("Gold Coin 10 Gm", "GC10"),
    ("Gold Coin 2 Gm", "GC2"),
    ("Gold Coin 20 Gm", "GC20"),
    ("Gold Coin 5 Gm", "GC5"),
    ("HAAR CHAIN 22", "HC22"),
    ("JHUMKA 22", "JB22"),
    ("KAAN CHAIN 22", "KC22"),
    ("LADIES BRACELET 18", "LB18"),
    ("LADIES BRACELET 22", "LB22"),
    ("LADIES KADA 22", "LK22"),
    ("LADIES RING 18", "LR18"),
    ("LADIES RING 22", "LR22"),
    ("LOCKET 18", "LC18"),
    ("LOCKET 22", "LC22"),
    ("MANGOTA 22", "MG22"),
    ("MOTI NATH 18", "MN18"),
    ("MS LONG 22", "ML22"),
    ("MSS-SHORT 20", "MS20"),
    ("MSS-SHORT 22", "MS22"),
    ("NATH 22", "NT22"),
    ("NECKLACE 22", "NK22"),
    ("NECKLACE SET 18", "NS18"),
    ("NECKLACE SET 22", "NS22"),
    ("PENDENT 18", "PD18"),
    ("PENDENT 22", "PD22"),
    ("PENDENT SET 18", "PS18"),
    ("PENDENT SET 22", "PS22"),
    ("TIKKA 22", "TK22"),
    ("TOPS 18", "TP18"),
    ("TOPS 22", "TP22"),
    ("WATI 22", "WT22"),
)

CATEGORIES: tuple[Category, ...] = tuple(Category(_key(label), label, prefix) for label, prefix in _ROWS)

assert len(CATEGORIES) == 57, f"expected 57 categories, got {len(CATEGORIES)}"
assert len({c.key for c in CATEGORIES}) == 57, "duplicate key"
assert len({c.prefix for c in CATEGORIES}) == 57, "duplicate prefix"

BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}
BY_PREFIX: dict[str, Category] = {c.prefix.upper(): c for c in CATEGORIES}

# Longest prefix first, so e.g. "GCM05" is tried before a shorter false match.
_PREFIX_RE = re.compile(
    "^(" + "|".join(sorted((re.escape(c.prefix) for c in CATEGORIES), key=len, reverse=True)) + r")[\s_/-]?\d+"
)


def category_from_tag_code(tag_code: str) -> Category | None:
    """Resolve a real tag code (e.g. "BG22/58", "bg22_58", "BG22-58") to its
    Category via prefix match. Returns None if no known prefix matches."""
    if not tag_code:
        return None
    m = _PREFIX_RE.match(tag_code.strip().upper())
    if not m:
        return None
    return BY_PREFIX.get(m.group(1))


def folder_label(category: Category) -> str:
    """Exact text used in a capture_intake tray folder name, e.g.
    '61 BANGLE 22' once numbered — this returns just the label part."""
    return category.label
