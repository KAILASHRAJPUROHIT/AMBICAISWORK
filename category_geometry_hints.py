"""Per-category true-3D-shape reminders for categories whose front-on capture
photo can be misread as a flatter shape than the piece actually is.

WHY THIS EXISTS: a bali (gold hoop earring) is captured photographed flat-on,
face toward the camera, because that's the only angle that shows its surface
design. But a hoop's REAL shape is a ring that curves away from the camera
and tapers as it wraps around, top and bottom -- not a flat strip. Nothing in
the reference photo itself tells the model this; a front-on photo of a hoop
and a front-on photo of a flat bar can look identical in outline. Confirmed
report from the catalogue owner (2026-08-15): edited bali images were coming
back as a flat single-line/strip design instead of a tapering circular hoop.

This is a per-CATEGORY fact, not something the reference photo's pixels can
answer (unlike reference_color_report, which measures real pixel colour) --
so it's a small static lookup, not a detector. Keep entries short: one
sentence appended to the prompt, matching the "don't add multiple lines"
constraint already established for reference_color_report's addendum.
"""
from __future__ import annotations

# Keyed on the canonical category strings from category_topology.py's
# CATEGORY_TOPOLOGY set. Add an entry here only when a real generation has
# actually shown the flattening failure for that category -- speculative
# entries for categories nobody has reported an issue on just add prompt
# length for no confirmed benefit.
_BALI_HINT = (
    "Highest-priority Bali view contract: present the matched pair in a decisive front "
    "three-quarter product view with each complete hoop plane yawed approximately 45 "
    "degrees relative to the camera. The camera sees the decorated front surface and a "
    "clearly receding side or rear surface together. A circular or polygonal hoop opening "
    "projects as a visibly narrow ellipse; a compact huggie opening reveals its front blade, "
    "side depth, rear arc, hinge, and clasp. Keep both earrings upright, level, equally sized, "
    "and consistently rotated. Image 1 is the exclusive authority for product identity, "
    "silhouette family, local cross-section, proportions, surface design, stone count, row "
    "layout, spacing, chains, dangles, engraving, filigree, and materials. When Image 2 is "
    "supplied, use it exclusively for the reviewed 45-degree camera orientation and pair "
    "spacing. Reproduce Image 1's flat planes and crisp corners where present, and its smooth "
    "rounded tubing where present. Use a 100 mm macro product lens at f/11, sharp focus "
    "throughout, bright diffused softbox lighting, and a seamless pure white background."
)

_ITEM_HINTS: dict[str, str] = {
    "BL18_10": (
        "Highest-priority subject and geometry for BL18_10: a matched pair of compact slim "
        "huggie earrings, each built from a tall narrow rectangular front blade with an "
        "approximately three-to-one height-to-width proportion. Four planar gold faces meet "
        "at crisp right-angle edges, creating the source's squared rectangular profile. The "
        "front blade remains dominant in the composition and carries one continuous dense "
        "pave panel from its flat top cap to its flat bottom cap: exactly two straight "
        "parallel columns of many tiny round white diamonds, matching Image 1's count, scale, "
        "spacing, sequence, white-metal setting, and very thin gold perimeter rails. The "
        "adjacent side is a narrow plain flat-gold plane. Present the pair from a front "
        "three-quarter camera angle at approximately 45 degrees, showing the decorated front "
        "blade and its narrow side plane together. Keep the inner opening compact and the "
        "rear arc, post, clasp, and hinge visually small and subordinate to the rectangular "
        "front blade. Use a 100 mm macro product lens at f/11, sharp focus throughout, bright "
        "softbox lighting, realistic 18-karat polished gold, and seamless pure white studio "
        "background. When Image 2 is supplied, use Image 1 exclusively for product identity, "
        "geometry, proportions, stones, settings, and materials; use Image 2 exclusively as "
        "the camera-angle and pair-spacing reference, copying its 45-degree front "
        "three-quarter orientation."
    ),
    "BL22_43": (
        "Highest-priority subject and geometry for BL22_43: a matched mirror-symmetric "
        "pair of slim 22-karat gold bali earrings with the exact gold-only construction "
        "shown in Image 1. Each earring has a tall narrow rectangular ribbon front that "
        "continues into a compact hoop, with a broad flat decorated face, crisp long side "
        "edges, and a narrow plain-gold side plane. Preserve Image 1's dense horizontal "
        "comb-cut line texture across the full face and its continuous raised curling "
        "vine-and-leaf motif down the centre, matching every engraved segment, opening, "
        "ridge, and bare-gold area. At the lower edge, preserve the wider two-level "
        "horizontal crossbar with exactly four rounded bead finials, one at each bar end. "
        "Below that crossbar preserve exactly five articulated gold link chains in the "
        "same graduated arrangement and exactly five terminal gold drops, with the centre "
        "chain longest and the outer chains progressively shorter. Present both earrings "
        "upright in a clear front three-quarter view at approximately 45 degrees, keeping "
        "the complete engraved front face readable while a narrow side plane and compact "
        "hoop opening establish depth. Every chain hangs naturally vertical. Use a 100 mm "
        "macro product lens at f/11, bright diffused softbox lighting, sharp focus, realistic "
        "polished 22-karat gold, and a seamless pure white studio background. Image 1 is "
        "the exclusive authority for product identity, proportions, engraving, component "
        "counts, construction, and materials. When Image 2 is supplied, use it exclusively "
        "for the reviewed 45-degree camera orientation and pair spacing; build every visible "
        "product feature from Image 1."
    ),
}

_GEOMETRY_HINTS: dict[str, str] = {
    "bali": _BALI_HINT,
    "bali_18": _BALI_HINT,
    "bali_22": _BALI_HINT,
    "ladies_bali": _BALI_HINT,
    "mens_bali": _BALI_HINT,
}


def hint_for(category: str | None, label: str | None = None) -> str | None:
    if not category:
        return None
    category_hint = _GEOMETRY_HINTS.get(category.strip().lower())
    if category_hint is None:
        return None
    item_hint = _ITEM_HINTS.get((label or "").strip().upper())
    # A measured item contract is more precise than the generic category
    # reminder and already includes the category's angle/depth requirements.
    # Sending both diluted BL18_10's slim rectangular geometry with generic
    # hoop language in repeated real tests.
    return item_hint or category_hint
