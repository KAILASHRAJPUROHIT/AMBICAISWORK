"""Reviewed secondary pose references for BFL catalogue generation.

Every current Bali SKU is assigned to a compatible 45-degree geometry family.
Image 1 and the prompt remain the exclusive product-design authority; these
guides supply camera orientation and pair spacing.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
_BALI_CATEGORIES = {"bali", "bali_18", "bali_22", "ladies_bali", "mens_bali"}
_PROFILE_GUIDES = {
    "compact_huggie": ROOT / "assets" / "geometry_guides" / "bali" / "compact_huggie_45.jpg",
    "round_hoop": ROOT / "assets" / "geometry_guides" / "bali" / "round_hoop_45.jpg",
}
_ITEM_GUIDES = {
    "BL22_43": ROOT / "assets" / "geometry_guides" / "bali" / "BL22_43_front45.jpg",
}
_ITEM_PROFILES = {
    # BALI 18
    "BL18_10": "compact_huggie",
    "BL18_16": "compact_huggie",
    "BL18_2": "compact_huggie",
    "BL18_29": "compact_huggie",
    "BL18_31": "round_hoop",
    "BL18_4": "compact_huggie",
    "BL18_45": "round_hoop",
    "BL18_51": "round_hoop",
    # BALI 22
    "BL22_102": "compact_huggie",
    "BL22_135": "compact_huggie",
    "BL22_16": "compact_huggie",
    "BL22_18": "compact_huggie",
    "BL22_24": "compact_huggie",
    "BL22_33": "round_hoop",
    "BL22_35": "compact_huggie",
    "BL22_36": "compact_huggie",
    "BL22_38": "round_hoop",
    "BL22_39": "compact_huggie",
    "BL22_40": "compact_huggie",
    "BL22_43": "compact_huggie",
    "BL22_44": "compact_huggie",
    "BL22_45": "round_hoop",
    "BL22_46": "round_hoop",
    "BL22_48": "round_hoop",
    "BL22_5": "compact_huggie",
    "BL22_51": "round_hoop",
    "BL22_52": "round_hoop",
    "BL22_60": "round_hoop",
    "BL22_64": "round_hoop",
    "BL22_66": "compact_huggie",
    "BL22_76": "round_hoop",
    "BL22_80": "compact_huggie",
    "BL22_86": "round_hoop",
}


class MissingBaliAngleProfile(RuntimeError):
    """Raised before a paid call when a Bali SKU lacks reviewed routing."""


def covered_labels() -> frozenset[str]:
    return frozenset(_ITEM_PROFILES)


def profile_for(category: str | None, label: str | None) -> str | None:
    if (category or "").strip().lower() not in _BALI_CATEGORIES:
        return None
    item = (label or "").strip().upper()
    profile = _ITEM_PROFILES.get(item)
    if profile is None:
        raise MissingBaliAngleProfile(
            f"BLOCKED_BEFORE_SPEND: Bali item {item or '<missing label>'} has no reviewed "
            "45-degree geometry profile"
        )
    return profile


def guide_for(category: str | None, label: str | None) -> Path | None:
    """Return the exact-item guide or its reviewed geometry-family guide."""

    profile = profile_for(category, label)
    if profile is None:
        return None
    item = (label or "").strip().upper()
    guide = _ITEM_GUIDES.get(item) or _PROFILE_GUIDES[profile]
    if not guide.is_file():
        raise FileNotFoundError(f"Reviewed catalogue reference guide is missing: {guide}")
    return guide.resolve()
