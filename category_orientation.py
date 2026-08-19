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
    # CORRECTED by owner (2026-08-19): MANGOTA is a kids' protection
    # bracelet/anklet (Nazariya evil-eye charm, black beads + gold/silver),
    # NOT a necklace -- an earlier guess (mango-motif necklace) was wrong
    # and has been corrected. Open curve like other flexible bead/chain
    # bracelets, worn on wrist or ankle.
    "mangota_22": OrientationGuide(OrientationType.OPEN_CURVE, "high"),

    # -- Studs / small flat earrings --
    "bali_18": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "bali_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
    "dull_22": OrientationGuide(OrientationType.FLAT_FACE_UP, "high"),
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


@dataclass(frozen=True, slots=True)
class CategoryProfile:
    """Wearer/body-part/expected-shape metadata, from
    docs/jewellery_category_orientation_reference.md's "Size & Wearer
    Reference" section (2026-08-19 sourced research -- real retailer
    listings where dimensions exist, honestly flagged "not found" where
    they don't, never invented). aspect_ratio is (min, max) WIDTH:HEIGHT
    as the piece would be laid/worn for the capture photo -- e.g. a
    bracelet's open curve reads much wider than tall (~3:1), a tikka's
    hook-chain-pendant reads much taller than wide (~1:5).

    confidence here is about the SIZE/SHAPE data specifically, not the
    orientation call in OrientationGuide above -- a category's orientation
    can be well-established while its aspect ratio is still a rough
    estimate (see the doc's own note on this). ``gate_worthy`` is a
    deliberately small, hand-picked subset (moderate/high confidence AND
    a ratio far enough from 1:1 that a wrong-shaped tracked blob is a real
    signal, not noise) -- built to catch the exact 2026-08-19 bracelet
    failure (tracker locked onto a thin highlight band, coverage/goldClip/
    sceneClip all read fine, nothing checked whether the TRACKED SHAPE
    looked like a bracelet at all) without adding false capture-blocks on
    categories whose true shape is closer to round/square (rings, studs)
    or whose size data is still too thin to trust as a gate.
    """
    wearer: str
    body_part: str
    aspect_ratio: tuple[float, float] | None  # (min W:H, max W:H), None if not established
    size_confidence: str  # "high" | "moderate" | "low" | "low-moderate"


PROFILES: dict[str, CategoryProfile] = {
    "baby_ring_22": CategoryProfile("babies-and-toddlers", "finger", (0.85, 1.15), "low"),
    "gents_ring_22": CategoryProfile("men", "finger", (0.85, 1.15), "moderate"),
    "ladies_ring_18": CategoryProfile("women", "finger", (0.85, 1.15), "moderate"),
    "ladies_ring_22": CategoryProfile("women", "finger", (0.85, 1.15), "moderate"),

    "baby_braclet_22": CategoryProfile("babies-and-toddlers", "wrist", (2.5, 3.5), "low"),
    "baby_kadli_22": CategoryProfile("babies-and-toddlers", "wrist", (0.85, 1.15), "moderate"),
    "bangle_22": CategoryProfile("women", "wrist", (0.85, 1.15), "moderate"),
    "gents_bracelet_22": CategoryProfile("men", "wrist", (3.0, 3.5), "high"),
    "gents_kada_18": CategoryProfile("men", "wrist", (0.85, 1.15), "moderate"),
    "gents_kada_22": CategoryProfile("men", "wrist", (0.85, 1.15), "moderate"),
    "ladies_bracelet_18": CategoryProfile("women", "wrist", (3.0, 3.5), "low-moderate"),
    "ladies_bracelet_22": CategoryProfile("women", "wrist", (3.0, 3.5), "low-moderate"),
    "ladies_kada_22": CategoryProfile("women", "wrist", (0.85, 1.15), "low"),
    "mangota_22": CategoryProfile("babies-and-toddlers", "wrist or ankle", (2.5, 3.5), "moderate"),

    "bali_18": CategoryProfile("women", "ear", (1.0, 1.3), "high"),
    "bali_22": CategoryProfile("women", "ear", (1.0, 1.3), "high"),
    "dull_22": CategoryProfile("women", "ear", (0.85, 1.15), "low"),
    "tops_18": CategoryProfile("women", "ear", (0.85, 1.15), "low-moderate"),
    "tops_22": CategoryProfile("women", "ear", (0.85, 1.15), "low-moderate"),

    "earring_22": CategoryProfile("women", "ear (hanging)", (0.33, 0.5), "low"),
    "jhumka_22": CategoryProfile("women", "ear (hanging)", (0.4, 0.5), "moderate"),
    "kaan_chain_22": CategoryProfile("women", "ear-to-hair", (0.067, 0.125), "moderate"),
    "moti_nath_18": CategoryProfile("women", "nose + ear-support", (1.5, 2.0), "low-moderate"),
    "nath_22": CategoryProfile("women", "nose", (1.5, 2.0), "low"),
    "tikka_22": CategoryProfile("women", "forehead / hair parting", (0.167, 0.25), "moderate"),

    "chain_22": CategoryProfile("unisex", "neck", (1.3, 1.8), "moderate"),
    "fancy_mala_18": CategoryProfile("women", "neck", (1.2, 1.6), "moderate"),
    "fancy_mala_22": CategoryProfile("women", "neck", (1.2, 1.6), "moderate"),
    "haar_chain_22": CategoryProfile("unisex/women", "neck", (1.3, 1.8), "low"),
    "ms_long_22": CategoryProfile("women", "neck", (1.3, 1.7), "moderate"),
    "mss_short_20": CategoryProfile("women", "neck", (1.2, 1.5), "moderate"),
    "mss_short_22": CategoryProfile("women", "neck", (1.2, 1.5), "moderate"),
    "necklace_22": CategoryProfile("women", "neck", (1.3, 1.7), "low-moderate"),
    "necklace_set_18": CategoryProfile("women", "neck + ears", (1.0, 1.3), "low"),
    "necklace_set_22": CategoryProfile("women", "neck + ears", (1.0, 1.3), "low"),

    "wati_22": CategoryProfile("women", "neck (pendant)", (2.0, 2.5), "high"),
    "locket_18": CategoryProfile("women", "neck (pendant)", (0.7, 0.85), "low"),
    "locket_22": CategoryProfile("women", "neck (pendant)", (0.7, 0.85), "low"),
    "pendent_18": CategoryProfile("women", "neck (pendant)", (0.6, 0.85), "high"),
    "pendent_22": CategoryProfile("women", "neck (pendant)", (0.6, 0.85), "high"),
    "pendent_set_18": CategoryProfile("women", "neck + ears", (0.7, 1.0), "low"),
    "pendent_set_22": CategoryProfile("women", "neck + ears", (0.7, 1.0), "low"),

    "baju_bandh_22": CategoryProfile("women", "upper arm / bicep", (2.0, 3.0), "low"),

    "gold_coin_22_kt": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_0_025_m": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_0_050_m": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_0_100_m": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_0_200_m": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_0_250_m": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_0_300_m": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_0_500_m": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_0_750_m": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_1_gm": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_10_gm": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_2_gm": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_20_gm": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
    "gold_coin_5_gm": CategoryProfile("unisex", "displayed flat", (0.85, 1.15), "high"),
}

# Hand-picked subset of PROFILES worth gating live capture on: moderate/high
# size-confidence AND a ratio far enough from 1:1 that a wrong-shaped
# tracked blob is a real signal. Deliberately excludes "low"/"low-moderate"
# confidence entries (the size data itself is too thin to block a real
# capture on) and near-1:1 shapes (rings/studs/gold coins -- little
# separation between "right shape" and "wrong shape" there, not worth the
# false-block risk). Built directly in response to the 2026-08-19 bracelet
# mis-framing: coverage/goldClip/sceneClip all read fine while the tracker
# had locked onto a thin sub-segment of the band, and nothing checked
# whether the tracked shape looked like a bracelet at all.
GATE_WORTHY_CATEGORIES = frozenset(
    key for key, p in PROFILES.items()
    if p.size_confidence in ("moderate", "high") and p.aspect_ratio is not None
    and (p.aspect_ratio[0] < 0.7 or p.aspect_ratio[1] > 1.4)
)


def profile_for(category_key: str) -> CategoryProfile | None:
    return PROFILES.get(category_key)
