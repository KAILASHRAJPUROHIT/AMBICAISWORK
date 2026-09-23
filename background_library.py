"""Category-aware recursive catalogue background discovery."""

from __future__ import annotations

import re
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# These products are all presented at a woman's ear. Keep one visual family
# even though stock and tag taxonomies use different product names.
EAR_WORN_MARKERS = (
    "earring", "tops", "jhumka", "bali", "dull", "kaan_chain",
    "kaanchain", "sui_dhaga", "suidhaga", "sui_dhaga",
)

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "baby_braclet_22": ("ladies_bracelet",),
    "baby_kadli_22": ("ladies_kada",),
    "baby_ring_22": ("ladies_rings",),
    "baju_bandh_22": ("bangles",),
    "bangle_22": ("bangles",),
    "bangles": ("bangles",),
    "chain_18": ("ladies_chains",),
    "chain_22": ("ladies_chains",),
    "ladies_chains": ("ladies_chains",),
    "gents_chains": ("gents_chains",),
    "haar_chain_22": ("necklace",),
    "fancy_mala_18": ("necklace",),
    "fancy_mala_22": ("necklace",),
    "gents_bracelet_18": ("gents_bracelet",),
    "gents_bracelet_22": ("gents_bracelet",),
    "gents_bracelet": ("gents_bracelet",),
    "ladies_bracelet_18": ("ladies_bracelet",),
    "ladies_bracelet_22": ("ladies_bracelet",),
    "ladies_bracelet": ("ladies_bracelet",),
    "gents_kada_18": ("gents_kada",),
    "gents_kada_22": ("gents_kada",),
    "gents_kada": ("gents_kada",),
    "ladies_kada_22": ("ladies_kada",),
    "ladies_kada": ("ladies_kada",),
    "gents_ring_22": ("gents_rings",),
    "gents_rings": ("gents_rings",),
    "ladies_ring_18": ("ladies_rings",),
    "ladies_ring_22": ("ladies_rings",),
    "ladies_rings": ("ladies_rings",),
    "locket_18": ("locket",),
    "locket_22": ("locket",),
    "locket": ("locket",),
    "ms_long_22": ("mangalsutra_long",),
    "mangalsutra_long": ("mangalsutra_long",),
    "mss_short_20": ("mangalsutra_short",),
    "mss_short_22": ("mangalsutra_short",),
    "mangalsutra_short": ("mangalsutra_short",),
    "necklace_22": ("necklace",),
    "necklace_set_18": ("necklace",),
    "necklace_set_22": ("necklace",),
    "necklace": ("necklace",),
    "pendent_18": ("pendant",),
    "pendent_22": ("pendant",),
    "pendent_set_18": ("pendant",),
    "pendent_set_22": ("pendant",),
    "pendant": ("pendant",),
    "silver": ("silver",),
    "diamond": ("diamond",),
    "wati_22": ("wati",),
    "wati": ("wati",),
}


def normalize_category(category: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(category).strip().casefold()).strip("_")


def keywords_for_category(category: str) -> tuple[str, ...]:
    key = normalize_category(category)
    if any(marker in key for marker in EAR_WORN_MARKERS):
        return ("earrings",)
    return CATEGORY_KEYWORDS.get(key, ())


def compatible_backgrounds(root: Path, category: str) -> list[dict[str, str]]:
    root = root.resolve()
    keywords = keywords_for_category(category)
    if not root.is_dir() or not keywords:
        return []
    matches: list[dict[str, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in IMAGE_EXTENSIONS:
            continue
        relative = path.relative_to(root)
        searchable = relative.as_posix().casefold()
        if not any(keyword.casefold() in searchable for keyword in keywords):
            continue
        parent = relative.parent.as_posix()
        matches.append({
            "path": relative.as_posix(),
            "name": path.stem,
            "style": "Backgrounds" if parent == "." else parent,
        })
    return sorted(matches, key=lambda row: (row["style"].casefold(), row["name"].casefold(), row["path"].casefold()))
