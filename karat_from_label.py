"""Derive an item's real karat (18 or 22) directly from its own tag label.

WHY THIS EXISTS: the catalogue prompt described every piece as "22-karat
gold" unconditionally. Confirmed as a real, systemic bug (2026-08-15): a
BALI 18 item (BL18_10, genuinely 18kt) was rendered and forced into the
22-karat description regardless -- this has been wrong for every 18kt
category run this whole session (LOCKET 18, LADIES RING 18, TOPS 18, BALI
18, etc.), not just this one test.

Every tag label in this business already encodes its own karat directly:
the two digits immediately after the alpha prefix are always the karat
marker -- ER22, JB22, LR18, BL18, BL22, LC18, TP18, WT22, PD22 and so on.
No lookup table needed; it's read straight off the label the same way the
existing prefix-parsing in ornament_code_map.py already relies on this
convention.
"""
from __future__ import annotations

import re

_KARAT_RE = re.compile(r"^[A-Za-z]+(\d{2})")
_KNOWN_KARATS = ("18", "22")


def karat_from_label(label: str) -> str | None:
    """Return "18" or "22" from a label like "BL18_10" or "ER22_65", or
    None if the label doesn't match the expected prefix+karat pattern or
    encodes a karat this business doesn't use."""
    match = _KARAT_RE.match((label or "").strip())
    if not match:
        return None
    karat = match.group(1)
    return karat if karat in _KNOWN_KARATS else None
