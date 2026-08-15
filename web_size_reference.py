"""
web_size_reference.py — free-form web search for typical real-world sizes of
a jewellery style/category, as a cross-check against tag-based photogrammetry
measurement (photogrammetry.py + jewellery_localization.py).

This does NOT measure the exact physical piece — it can't; small-batch
jewellery has no published spec sheet online. It gives a category/style
AVERAGE range (e.g. "single mango pendants typically run 4-8cm"), which is
weaker signal than a direct measurement but useful as a sanity bound: if the
tag-calibrated measurement for THIS piece is wildly outside the style's
normal range, that's worth flagging rather than trusting silently — exactly
the kind of check that would have caught LC22_11's ~11cm measured pendant
against a ~6cm real-world reference (2026-08-02).

Uses ddgs (free, no API key) — results are text snippets from search result
pages, parsed for size mentions with a plain regex. This is heuristic, not
authoritative: search snippets are noisy, sizes are reported in inconsistent
units and contexts (chain length vs pendant length vs total drop). Treat
extracted values as a rough candidate range, not a precise figure.
"""

import re
import time

_SIZE_PATTERN = re.compile(
    r'(\d+(?:\.\d+)?)\s*(cm|mm|inch(?:es)?|"|in\.)\b', re.IGNORECASE
)

_UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "inch": 25.4, "inches": 25.4, '"': 25.4, "in.": 25.4}


def _extract_sizes_mm(text: str) -> list:
    sizes = []
    for value, unit in _SIZE_PATTERN.findall(text or ""):
        unit_key = unit.lower().rstrip(".")
        mm_per_unit = _UNIT_TO_MM.get(unit_key) or _UNIT_TO_MM.get(unit.lower())
        if mm_per_unit is None:
            continue
        mm = float(value) * mm_per_unit
        # Discard values outside any plausible jewellery-component range —
        # a "24 inch" necklace CHAIN length mention is real text but not a
        # pendant/motif size; keep only what could plausibly be a single
        # component (a bangle diameter is the upper realistic bound here).
        if 3.0 <= mm <= 120.0:
            sizes.append(mm)
    return sizes


def search_size_reference(category: str, style_hint: str = "", weight_g: float = None,
                          max_results: int = 5) -> dict:
    """Search for typical real-world size of this jewellery style/category.
    Returns {"ok": True, "sizes_mm": [float, ...], "median_mm": float,
    "sources": [{"title": str, "url": str}, ...]} or {"ok": False, "reason": str}.

    style_hint: a short design descriptor (e.g. "paisley mango pendant",
    "openwork stud earring") — narrows the search past just the raw category
    name, since "locket" alone returns too broad a size range to be useful.

    Scoped specifically to Indian jewellery — this business sells 22k gold
    Indian designs (jhumka, bali, mangalsutra, haar, etc.), which run
    different typical proportions than generic/western gold jewellery.
    Resolves `category` through ornament_placement's real product name
    (e.g. "ladies_bali" -> "Ladies Bali") so the query uses the actual
    Indian jewellery term, not our internal category slug, and explicitly
    anchors every query to "22k Indian gold" so results stay in the right
    market segment rather than drifting to Western/generic gold jewellery
    (which has meaningfully different typical sizing conventions).
    """
    display_name = category
    try:
        import ornament_placement as op
        display_name = op.get_profile(category).name
    except Exception:
        pass

    query_parts = [
        "22k Indian gold", display_name, style_hint,
        "typical size dimensions cm",
    ]
    query = " ".join(p for p in query_parts if p)
    if weight_g:
        query = f"{query} {weight_g:.1f} grams"

    try:
        from ddgs import DDGS
        with DDGS() as d:
            results = list(d.text(query, max_results=max_results))
    except Exception as e:
        return {"ok": False, "reason": f"search error: {e}"}

    if not results:
        return {"ok": False, "reason": "no search results"}

    all_sizes = []
    sources = []
    for r in results:
        text = f"{r.get('title', '')} {r.get('body', '')}"
        found = _extract_sizes_mm(text)
        if found:
            all_sizes.extend(found)
            sources.append({"title": r.get("title", ""), "url": r.get("href", "")})

    if not all_sizes:
        return {"ok": False, "reason": "no parseable size mentions in results",
                "raw_result_count": len(results)}

    all_sizes.sort()
    median = all_sizes[len(all_sizes) // 2]
    return {"ok": True, "sizes_mm": all_sizes, "median_mm": round(median, 1),
            "sources": sources, "query": query}
