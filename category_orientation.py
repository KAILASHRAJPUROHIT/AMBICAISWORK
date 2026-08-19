"""
Machine-readable rotation guidance per stock category, derived from
docs/jewellery_category_orientation_reference.md (2026-08-19 revision,
full 57-category research). That doc has the sourcing/confidence detail
and reference URLs per category; this module carries only the
ROTATION-RELEVANT verdict so sam_locate.py/capture_tool.py can act on it
without parsing markdown.

Keyed by ornament_code_map.Category.key (snake_case of the exact stock
label), so a category resolved from a scanned tag code maps straight into
an OrientationGuide via orientation_for().
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OrientationType(Enum):
    # Rings, bangles, kada, bracelets, tops, bali, coins, pendants/lockets.
    # Lies flat; only a small "which way is level" correction is needed,
    # never an axis-forcing rotation. sam_locate's existing minAreaRect
    # nearest-correction behaviour already does the right thing here.
    FLAT_FACE_UP = "flat_face_up"

    # Earrings/jhumka/nath/tikka/kaan chain: has a real hanging direction
    # (attachment point up, ornament extending down) that must be forced,
    # not just nudged toward the nearest right angle -- see
    # sam_locate._upright_angle's prefer_vertical mode.
    HANGS_VERTICAL = "hangs_vertical"

    # Necklaces/chains/mala/mangalsutra: laid as a symmetric curve, no
    # strong single-axis preference to force. Left as captured.
    SYMMETRIC_CURVE = "symmetric_curve"

    # Bracelets/baju bandh: open curve, similarly no strong axis to force.
    OPEN_CURVE = "open_curve"


@dataclass(frozen=True, slots=True)
class OrientationGuide:
    orientation: OrientationType
    confidence: str  # "high" | "moderate" | "low"


GUIDES: dict[str, OrientationGuide] = {
    # -- Rings --
    "baby_ring_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "moderate"),
    "gents_ring_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "ladies_ring_18": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "ladies_ring_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),

    # -- Bangles, kada, bracelets --
    "baby_braclet_22": OrientationGuide(OrientationType.OPEN_CURVE, "moderate"),
    "baby_kadli_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "bangle_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gents_bracelet_22": OrientationGuide(OrientationType.OPEN_CURVE, "moderate"),
    "gents_kada_18": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gents_kada_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "ladies_bracelet_18": OrientationGuide(OrientationType.OPEN_CURVE, "moderate"),
    "ladies_bracelet_22": OrientationGuide(OrientationType.OPEN_CURVE, "moderate"),
    "ladies_kada_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),

    # -- Studs / small flat earrings --
    "bali_18": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "bali_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "dull_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "low"),
    "tops_18": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "tops_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),

    # -- Dangling / hanging earrings and ear ornaments --
    "earring_22": OrientationGuide(OrientationType.HANGS_VERTICAL, "high"),
    "jhumka_22": OrientationGuide(OrientationType.HANGS_VERTICAL, "high"),
    "kaan_chain_22": OrientationGuide(OrientationType.HANGS_VERTICAL, "moderate"),
    "moti_nath_18": OrientationGuide(OrientationType.HANGS_VERTICAL, "moderate"),
    "nath_22": OrientationGuide(OrientationType.HANGS_VERTICAL, "moderate"),
    "tikka_22": OrientationGuide(OrientationType.HANGS_VERTICAL, "high"),

    # -- Necklaces, chains, mala, mangalsutra --
    "chain_22": OrientationGuide(OrientationType.SYMMETRIC_CURVE, "high"),
    "fancy_mala_18": OrientationGuide(OrientationType.SYMMETRIC_CURVE, "moderate"),
    "fancy_mala_22": OrientationGuide(OrientationType.SYMMETRIC_CURVE, "moderate"),
    "haar_chain_22": OrientationGuide(OrientationType.SYMMETRIC_CURVE, "moderate"),
    "mangota_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "low"),
    "ms_long_22": OrientationGuide(OrientationType.SYMMETRIC_CURVE, "high"),
    "mss_short_20": OrientationGuide(OrientationType.SYMMETRIC_CURVE, "high"),
    "mss_short_22": OrientationGuide(OrientationType.SYMMETRIC_CURVE, "high"),
    "necklace_22": OrientationGuide(OrientationType.SYMMETRIC_CURVE, "high"),
    "necklace_set_18": OrientationGuide(OrientationType.SYMMETRIC_CURVE, "high"),
    "necklace_set_22": OrientationGuide(OrientationType.SYMMETRIC_CURVE, "high"),

    # -- Pendants, lockets, pendant sets --
    "locket_18": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "locket_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "pendent_18": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "pendent_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "pendent_set_18": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "pendent_set_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),

    # -- Armlet --
    "baju_bandh_22": OrientationGuide(OrientationType.OPEN_CURVE, "moderate"),

    # -- Ground truth: WATI is the twin-bowl mangalsutra pendant --
    "wati_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),

    # -- Gold coins: flat, face up, embossed motif toward camera --
    "gold_coin_22_kt": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_0_025_m": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_0_050_m": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_0_100_m": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_0_200_m": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_0_250_m": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_0_300_m": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_0_500_m": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_0_750_m": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_1_gm": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_10_gm": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_2_gm": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_20_gm": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "gold_coin_5_gm": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
}


def orientation_for(category_key: str) -> OrientationGuide:
    """Falls back to FLAT_FACE_UP/low for an unknown key -- the safer
    default (a small nearest-axis nudge, never an axis-forcing rotation)
    when a category isn't recognised, rather than guessing a hanging
    orientation that could actively rotate an unfamiliar item the wrong
    way."""
    return GUIDES.get(category_key, OrientationGuide(OrientationType.FLAT_FACE_UP, "low"))
