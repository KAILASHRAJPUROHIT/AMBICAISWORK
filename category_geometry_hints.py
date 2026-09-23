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

# Confirmed live 2026-09-08: earring/tops-family renders were coming back
# showing only ONE earring instead of the matched pair the physical item
# actually is (category_topology.py's own _PAIR set already knows earrings,
# tops, jhumka and dull ship as two pieces -- but that classification was
# never wired into the prompt, so FLUX had no reason to know there should be
# two). Unlike _BALI_HINT (a hoop that curves away from camera and needs an
# opening/ellipse projection called out), these are small flat/compact
# stud-and-drop earrings -- the geometry risk here isn't shape-flattening,
# it's the model treating the reference photo of two earrings as one subject
# and rendering only one. So this hint's job is narrower: state the pair
# count explicitly and require both pieces in the same frame.
_SMALL_PAIR_HINT = (
    "Highest-priority pair contract: the physical item is a matched PAIR of two separate "
    "earrings, not one. Render both earrings together in a single frame, side by side, "
    "upright, level, equally sized, mirror-matched, and consistently rotated -- never crop, "
    "merge, or drop either piece down to a single earring. These are small compact stud or "
    "drop-style earrings, so use a close macro product framing that keeps both complete "
    "pieces fully visible with clear even spacing between them, not a single-earring "
    "close-up. Image 1 is the exclusive authority for product identity, silhouette, "
    "proportions, stone count, setting, engraving, and materials, applied identically to "
    "both earrings. When Image 2 is supplied, use it exclusively for the reviewed camera "
    "angle and pair spacing. Use a 100 mm macro product lens at f/11, sharp focus "
    "throughout, bright diffused softbox lighting, and a seamless pure white studio "
    "background."
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

_RING_HINT = (
    "Ring shank contract: this is a finger ring, so show the complete ring, not the "
    "decorated head alone. Present it in a front three-quarter product view with the "
    "head upright and facing the camera, and the band continuing out of the head on "
    "both sides and curving away behind it, its far side visible as a narrower arc "
    "receding from the camera. The finger opening reads as a real opening with depth. "
    "Every ring has a band, so draw the complete band in every case: where Image 1 "
    "crops it away, hides it behind the stand, or shows only a short fragment, "
    "continue that fragment into a full, smoothly tapering band of the same width, "
    "metal, and finish, closing the circle behind the head. This completes a part of "
    "the piece the photograph did not show, and is not an added component. Where the "
    "band IS visible, keep its width, taper, and surface work exactly as Image 1 has them."
)

_GEOMETRY_HINTS: dict[str, str] = {
    "bali": _BALI_HINT,
    "bali_18": _BALI_HINT,
    "bali_22": _BALI_HINT,
    "ladies_bali": _BALI_HINT,
    "mens_bali": _BALI_HINT,
    # Rings were rendering as a floating ornament head with the shank dropped
    # entirely (LR22_95, confirmed by the catalogue owner 2026-09-01 against an
    # earlier render that kept it). A ring photographed head-on gives the model
    # no reason to know a band continues behind -- the same blind spot the bali
    # hoop hint exists for.
    "ladies_ring_22": _RING_HINT,
    "ladies_ring_18": _RING_HINT,
    "ladies_rings": _RING_HINT,
    "gents_ring_22": _RING_HINT,
    "gents_rings": _RING_HINT,
    "baby_ring_22": _RING_HINT,
    # Small earring-family categories that category_topology.py's _PAIR set
    # already knows always ship as two pieces (see _SMALL_PAIR_HINT above).
    "earring_22": _SMALL_PAIR_HINT,
    "earring_18": _SMALL_PAIR_HINT,
    "tops_22": _SMALL_PAIR_HINT,
    "tops_18": _SMALL_PAIR_HINT,
    "jhumka_22": _SMALL_PAIR_HINT,
    "dull_22": _SMALL_PAIR_HINT,
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
