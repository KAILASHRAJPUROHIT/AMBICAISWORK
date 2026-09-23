"""Measurable catalogue-image rules for AI jewellery composites.

The framing thresholds follow Google Merchant Center's product-image guidance:
the product should occupy 75–90% of the full image. For jewellery, occupancy
is measured on the dominant side of the segmented ornament bounding box. An
area percentage would unfairly reject long chains, narrow bangles, and pairs
of earrings even when they are correctly prominent in the frame.

The 75–90% rule is for the studio/product image only. Model images retain
natural worn scale and use their category/pose checks instead.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


STUDIO_FILL_MIN = 0.75
STUDIO_FILL_MAX = 0.90


@dataclass(frozen=True, slots=True)
class StudioFrameCheck:
    ok: bool
    verified: bool
    bbox: tuple[int, int, int, int] | None
    width_fill: float | None
    height_fill: float | None
    dominant_fill: float | None
    touches_edge: bool | None
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_studio_bbox(
    image_size: tuple[int, int],
    bbox: tuple[int, int, int, int] | None,
) -> StudioFrameCheck:
    """Evaluate a segmented ornament box without doing any AI inference."""

    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    if bbox is None:
        return StudioFrameCheck(
            ok=False,
            verified=False,
            bbox=None,
            width_fill=None,
            height_fill=None,
            dominant_fill=None,
            touches_edge=None,
            reason="Jewellery foreground could not be segmented",
        )

    left, top, right, bottom = bbox
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError(f"invalid bbox {bbox!r} for image {image_size!r}")
    width_fill = (right - left) / width
    height_fill = (bottom - top) / height
    dominant_fill = max(width_fill, height_fill)
    touches_edge = left == 0 or top == 0 or right == width or bottom == height

    failures = []
    if dominant_fill < STUDIO_FILL_MIN:
        failures.append(
            f"jewellery fills {dominant_fill:.1%}; minimum is {STUDIO_FILL_MIN:.0%}"
        )
    elif dominant_fill > STUDIO_FILL_MAX:
        failures.append(
            f"jewellery fills {dominant_fill:.1%}; maximum is {STUDIO_FILL_MAX:.0%}"
        )
    if touches_edge:
        failures.append("segmented jewellery touches the frame edge")

    return StudioFrameCheck(
        ok=not failures,
        verified=True,
        bbox=bbox,
        width_fill=round(width_fill, 4),
        height_fill=round(height_fill, 4),
        dominant_fill=round(dominant_fill, 4),
        touches_edge=touches_edge,
        reason="; ".join(failures) if failures else "Studio framing is within 75–90%",
    )


def inspect_studio_frame(path: str | Path) -> StudioFrameCheck:
    """Segment the studio ornament locally and enforce its frame occupancy."""

    import design_verify_local

    try:
        image_size, bbox = design_verify_local.foreground_bbox(str(path))
        return evaluate_studio_bbox(image_size, bbox)
    except Exception as exc:
        return StudioFrameCheck(
            ok=False,
            verified=False,
            bbox=None,
            width_fill=None,
            height_fill=None,
            dominant_fill=None,
            touches_edge=None,
            reason=f"Framing check unavailable: {type(exc).__name__}: {exc}",
        )


STUDIO_PROMPT_RULES = (
    "OUTPUT FRAMING — MEASURABLE REQUIREMENT:\n"
    "- Output a square 1:1 image. Keep the complete jewellery visible and centred.\n"
    "- The jewellery's overall bounding box (the pair together when sold as a pair) "
    "must fill 75–90% of the image along its longest dimension.\n"
    "- Keep the complete jewellery — every piece of a pair, spread apart or not — "
    "fully inside the frame, with a visible plain margin of at least 5% of the "
    "image width between the nearest metal, chain, stone, clasp or dangle and "
    "every edge: left, right, top and bottom.\n"
    "- Keep every piece perfectly upright and level, with no tilt or rotation. "
    "Centre a single piece with equal empty space on all four sides. For a "
    "matched pair, render both pieces at the exact same size, with their top "
    "points aligned to the same horizontal line — no more than a 2% "
    "difference in height or scale between the two pieces.\n"
    "- The metal is warm yellow gold throughout, a rich, deep 22K golden tone "
    "— not pale, washed out, orange or red. Bright white highlights anywhere "
    "on the metal are gold catching studio light, not a different silver or "
    "white-gold material — never split one piece into separate gold and "
    "silver sections. (If the source is genuinely silver, white gold or "
    "rhodium instead, keep it cool silver-white throughout instead — but "
    "never invent a two-tone split that is not in the source.)\n"
    "- Photograph the metal as a real polished object, not a 3D render or "
    "CGI: each curved surface reflects the studio light as a bright specular "
    "highlight beside deeper rich amber shadow in the recesses — never a "
    "flat, even, waxy or plastic-looking gradient.\n"
    "- Do not crop the ornament itself and do not stretch it to reach the target.\n"
)


STRAIGHT_CENTERED_RULE = (
    "Keep every piece perfectly upright and level, with no tilt or rotation. "
    "Centre a single piece with equal empty space on all four sides. For a "
    "matched pair, render both pieces at the exact same size, with their top "
    "points aligned to the same horizontal line — no more than a 2% "
    "difference in height or scale between the two pieces."
)


GOLD_COLOR_RULE = (
    "The metal is warm yellow gold throughout, a rich, deep 22K golden tone "
    "— not pale, washed out, orange or red. Bright white highlights anywhere "
    "on the metal — the dome, the connector, the fringe, any polished "
    "surface — are gold catching studio light, not a different silver or "
    "white-gold material. Render every part in one consistent warm "
    "yellow-gold; never split the piece into separate gold and silver "
    "sections. Photograph it as a real polished object, not a 3D render or "
    "CGI: each curved surface reflects the studio light as a bright "
    "specular highlight beside deeper rich amber shadow in the recesses — "
    "never a flat, even, waxy or plastic-looking gradient."
)


MODEL_PROMPT_RULES = (
    "OUTPUT FRAMING — MEASURABLE REQUIREMENT:\n"
    "- Output a square 1:1 image using a centred crop of the requested model pose.\n"
    "- Keep the jewellery, its attachment point, and the body zone needed to understand "
    "how it is worn fully visible.\n"
    "- Preserve realistic worn scale. The 75–90% product-only rule does not apply to "
    "on-model images.\n"
    "- Do not crop through the jewellery or let any part of it touch an image edge.\n"
)


def is_plain_white_background(bg_path: str) -> bool:
    """True when bg_path is a near-uniform white/seamless plate (the
    "Studio Mode White" style, 2026-08-03) rather than a real prop scene.
    Checked by actual pixel statistics, not filename/style-key string
    matching, so it stays correct even if the file is swapped or renamed —
    mean brightness near white and low variance (no visible prop edges,
    shadows, or texture) is what actually distinguishes a blank plate from
    a real scene. Fails open (False) on any read error: worst case falls
    back to the existing prop-aware instructions, which is the safe
    default that's been in production."""
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(bg_path).convert("L")
        arr = np.asarray(img, dtype=float)
        return float(arr.mean()) > 245 and float(arr.std()) < 8
    except Exception:
        return False


def _klein_pair_and_disambiguation(category: str, profile) -> tuple[str, str]:
    """Shared helper for both Klein prompts below. Returns (pair_line,
    disambiguation_line), each empty-string when not applicable to this
    category — never a universal sentence forced onto every category."""
    pair_line = ""
    if profile.set_rule:
        pair_rule = profile.set_rule.strip().replace("Image 1", "the reference")
        pair_line = f" {pair_rule}"

    disambiguation = ""
    if category.strip().lower() == "wati":
        disambiguation = (
            " This is Maharashtrian mangalsutra jewellery, not a bowl, "
            "plate, container, toe ring or display prop."
        )
    return pair_line, disambiguation


def _klein_shape_lock(profile) -> str:
    """Short category-specific topology constraints for the 4B editor."""
    key = profile.key
    if key in {"earrings", "tops", "jhumka", "dul", "kaan_chain"}:
        return (
            " Treat each earring as one complete inseparable top-to-bottom assembly. "
            "The two earrings are a matched pair and must retain identical component "
            "topology: the same component types, count and order on both sides. If a "
            "tag obscures part of one earring, use the clearer matching earring only "
            "to restore that corresponding hidden part. Never invent a different "
            "connector type, extra chain links or a different intermediate section. "
            "Choose whichever side has the highest visible match confidence as the "
            "topology authority, then replicate that component structure left-to-right "
            "or right-to-left onto its mate while preserving the mate's correct "
            "left/right orientation, lighting and viewpoint. "
            "Transfer every visible component in its original order, from the "
            "topmost stud or ornament through every connector to the lowest visible "
            "drop, bead or bell. Attach the stand only at or behind the topmost "
            "component. Never discard the upper design, attach the stand directly "
            "to a lower bell, shorten the assembly or substitute components."
        )
    if key in {"ring", "ladies_rings", "gents_rings", "baby_ring"}:
        return (
            " Preserve the ring topology: one continuous finger band/shank and "
            "its visible design exactly. Retain every visible band edge and any "
            "visible central opening. Never flatten it into a brooch, cuff, coin "
            "or pendant. If the source holder hides part of the band, continue "
            "only a plain matching-metal continuation so it remains a physical "
            "finger ring. A flat decorated band must remain a flat decorated band: "
            "never add a crown, solitaire, centrepiece, motif or stone unless that "
            "exact element is visibly present in the source. Preserve every visible "
            "band path and its crossing order. If the source is an open bypass or "
            "wraparound ring with overlapping unjoined ends, keep those ends open, "
            "overlapping and unjoined; never straighten them into parallel stacked "
            "rings or fuse them into one band. Bright white, silver or dark oval "
            "sections may be reflective two-tone metal endcaps: treat them as stones "
            "only when the source clearly shows gemstone facets and a physical stone "
            "setting. Preserve contrasting metal endcaps and never replace them with "
            "diamonds or gems."
        )
    if key in {"bali", "ladies_bali", "mens_bali", "nath", "moti_nath"}:
        return " Preserve each hoop's circular opening and attachment ends; never close, flatten or fill the opening."
    if key == "locket":
        return " Preserve the locket hinge, seam, bail and closure; never convert it into a solid pendant."
    if key in {"chain", "ladies_chains", "gents_chains", "fancy_mala", "haar_chain", "mangalsutra_long", "mangalsutra_short"}:
        return " Preserve every visible link, bead sequence, terminal fitting and connection; never fuse or shorten the chain."
    if key == "gold_coin":
        return " Preserve the complete circular coin edge and exact visible relief; never add a bail, chain, band or jewellery mount."
    if key in {"necklace_set", "pendant_set"}:
        return " Preserve the identity, separation and exact count of every set component."
    return ""


def _klein_short_earring_isolation_prompt(profile) -> str | None:
    """Return a positive 30-80 word isolation prompt for one earring type."""
    description = profile.meaning or profile.name
    if profile.key == "tops":
        structure = (
            "Preserve two complete front-facing studs, each as one connected "
            "object with its photographed silhouette, orientation, materials, "
            "colours, stone arrangement and proportions."
        )
    elif profile.key in {"jhumka", "dul"}:
        structure = (
            "Preserve two complete top-to-bottom assemblies, each running from "
            "its top stud through every visible connector and bell to its lowest "
            "bead fringe, in the photographed order."
        )
    elif profile.key in {"bali", "ladies_bali", "mens_bali"}:
        structure = (
            "Preserve two complete hoops with their photographed circular "
            "openings, attachment ends, orientation, materials, colours and "
            "proportions."
        )
    elif profile.key in {"earrings", "kaan_chain"}:
        structure = (
            "Preserve two complete top-to-bottom assemblies, each running from "
            "its top stud through every visible connector and motif to its lowest "
            "drop, in the photographed order."
        )
    else:
        return None
    return (
        f"Create a clean product reference containing the exact matched pair of "
        f"{description} from the source, centred on solid white. Remove the "
        f"display stand, holder, tray, hand, tag and background from the source, "
        f"and keep the complete pair fully inside the frame with a plain margin "
        f"of at least 5% of the image width on every side. {STRAIGHT_CENTERED_RULE} "
        f"{GOLD_COLOR_RULE} "
        f"{structure} "
        f"Keep both earrings equal in size and identical in design."
    )


def _klein_short_earring_edit_prompt(profile) -> str | None:
    """Return a positive 30-80 word placement prompt for one earring type."""
    description = profile.meaning or profile.name
    if profile.key == "tops":
        placement = "pinned flat to the front face of the horizontal T-bar"
        structure = (
            "Preserve two complete front-facing studs as single connected "
            "objects in their photographed orientation"
        )
    elif profile.key in {"jhumka", "dul"}:
        placement = "hanging from the two ends of the T-stand"
        structure = (
            "Preserve each complete top-to-bottom assembly from its stud through "
            "every connector and bell to its lowest bead fringe"
        )
    elif profile.key in {"bali", "ladies_bali", "mens_bali"}:
        placement = "hanging from the two ends of the T-stand"
        structure = (
            "Preserve both complete hoops, their circular openings and their "
            "photographed attachment ends"
        )
    elif profile.key in {"earrings", "kaan_chain"}:
        placement = "hanging from the two ends of the T-stand"
        structure = (
            "Preserve each complete top-to-bottom assembly from its stud through "
            "every connector and motif to its lowest drop"
        )
    else:
        return None
    return (
        f"Place the exact matched pair of {description} from the left reference "
        f"{placement} in the right scene, one earring at each end. {structure}, "
        f"with equal size and identical design. Match only the destination "
        f"lighting, scale, contact shadow and background. {GOLD_COLOR_RULE}"
    )


def build_klein_isolation_prompt(category: str) -> str:
    """STAGE 1 of the two-stage Klein pipeline — raw jewellery photo (with
    hand/tray/stand/tag clutter) -> clean jewellery isolated on white.

    Kept as a SEPARATE prompt/stage from build_klein_edit_prompt() (stage 2)
    deliberately: the original single combined prompt asked one 4B model
    invocation to isolate, inspect, reconstruct, AND composite all at once —
    instruction overload for a small distilled model. Splitting into two
    focused single-purpose calls (confirmed working live 2026-08-03 on
    TP18_8.jpg and LR22_439/436.jpg — see HANDOVER_2026-08-03.md §27) gave
    noticeably better results than the combined version."""
    from ornament_placement import get_profile
    profile = get_profile(category.lower().strip())
    short_prompt = _klein_short_earring_isolation_prompt(profile)
    if short_prompt:
        return short_prompt
    description = profile.meaning or profile.name
    pair_line, disambiguation = _klein_pair_and_disambiguation(category, profile)
    shape_lock = _klein_shape_lock(profile)
    return (
        f"Indian jewellery isolation. Keep only the exact {description} visible "
        f"in the source image. Preserve the exact number of pieces, silhouette, "
        f"proportions, orientation, curves, engraving, cut-outs, metal and enamel "
        f"colours, stone count, stone shapes, settings, spacing and every original "
        f"visible component. Do not duplicate, remove, invent, simplify, mirror or "
        f"redesign anything. Remove everything that is not part of the jewellery: "
        f"the display stand or holder, tag, thread, hand, surface, background and "
        f"unrelated shadows. Present only the isolated jewellery centred on a plain "
        f"solid white background. Add no text, logo, watermark, label or AI badge. "
        f"{STRAIGHT_CENTERED_RULE} {GOLD_COLOR_RULE}"
        f"{shape_lock}{pair_line}{disambiguation}"
    )


def build_klein_edit_prompt(category: str) -> str:
    """STAGE 2 of the two-stage Klein pipeline — an already-isolated
    jewellery cutout (left half) + a real destination catalogue background
    (right half) -> final composited catalogue image.

    Rewritten 2026-08-03 to fix real contradictions found in the prior
    single-stage version: (1) it told stage 2 to "cut out" jewellery even
    though the left image was ALREADY the clean cutout by this point; (2) it
    said both "no simplifying" and "redraw it" in the same prompt — direct
    self-contradiction; (3) the wati bowl/container disambiguation was a
    universal string appended to every category, not just wati. This version
    frames the left image explicitly as "the design authority" to transfer,
    not something to still be extracted, and never uses "redraw"/"cut out"
    language for stage 2 at all."""
    from ornament_placement import get_profile, studio_guidance
    profile = get_profile(category.lower().strip())
    short_prompt = _klein_short_earring_edit_prompt(profile)
    if short_prompt:
        return short_prompt
    description = profile.meaning or profile.name
    pair_line, disambiguation = _klein_pair_and_disambiguation(category, profile)
    shape_lock = _klein_shape_lock(profile)
    placement = studio_guidance(category).replace("\n", " ")
    return (
        f"Indian jewellery catalogue edit. The left half contains an "
        f"already-isolated reference of {description}; it is the exact design "
        f"authority. Transfer only that jewellery into the right-half catalogue "
        f"scene. Preserve the exact number of pieces, silhouette, proportions, "
        f"orientation, curves, engraving, cut-outs, metal and enamel colours, "
        f"stone count, stone shapes, settings, spacing and every visible "
        f"component. Do not duplicate, remove, mirror, simplify, soften, invent "
        f"or redesign anything. Place the jewellery naturally on the existing "
        f"display prop at a realistic scale. Match the right-side scene's "
        f"perspective, reflections, contact shadow and lighting without changing "
        f"the jewellery's design or original colours. Keep the right-side "
        f"background, prop, crop and composition unchanged. Do not erase, replace, "
        f"resize or redesign the existing stand, holder, pedestal or support. "
        f"Add no text, logo, watermark, label or AI badge. {GOLD_COLOR_RULE} {placement}"
        f"{shape_lock}{pair_line}{disambiguation}"
    )


def build_klein_raw_edit_prompt(category: str) -> str:
    """Compact positive ring edit prompt for distilled FLUX.2 Klein.

    Keep this category-only baseline factual. Image-specific topology facts are
    supplied separately through ``model_prompt_override`` after visual review.
    """
    from ornament_placement import get_profile

    profile = get_profile(category.lower().strip())
    description = profile.meaning or profile.name
    return (
        f"Place the exact {description} from the left reference upright on the "
        f"ring box in the right scene. Preserve its photographed silhouette, "
        f"topology, materials, colours, visible design and orientation. Keep the "
        f"jewellery design unchanged. Match only the destination lighting, scale, "
        f"contact shadow and background. {GOLD_COLOR_RULE}"
    )


def build_klein_white_product_prompt(category: str, design: dict | None = None) -> str:
    """One-stage positive white prompt, optionally grounded by a design record.

    BFL's own Klein Space asks its image-aware prompt rewriter for one clear,
    analytical 50-80 word instruction. Keep only the highest-value visible
    facts here; the structured record remains the full verification contract.
    """
    from ornament_placement import get_profile

    profile = get_profile(category.lower().strip())
    if design:
        quantity = max(1, int(design.get("quantity") or 1))
        item_type = design.get("item_type") or profile.name.lower()
        relation = (
            f"exactly {quantity} separate matching {item_type}"
            if quantity > 1 and design.get("pair")
            else f"exactly {quantity} {item_type}"
        )
        # This branch actually knows the real metal (design.get("metal_colour")),
        # unlike the other three prompt paths that share the generic,
        # gold-assuming GOLD_COLOR_RULE constant — so build a data-aware
        # version instead of asserting "yellow gold" over a genuinely silver
        # or white-gold record.
        record_metal = str(design.get("metal_colour") or "").strip().lower()
        if "silver" in record_metal or "white gold" in record_metal or "rhodium" in record_metal:
            metal_colour_rule = (
                "The metal is cool silver-white throughout. Bright highlights "
                "anywhere on the metal are this same silver-white metal "
                "catching studio light, not a different gold material. "
                "Render every part in one consistent silver-white; never add "
                "gold-coloured sections."
            )
        elif "rose gold" in record_metal:
            metal_colour_rule = (
                "The metal is warm rose gold (pink-toned) throughout. Bright "
                "highlights anywhere on the metal are this same rose gold "
                "catching studio light, not a different material. Render "
                "every part in one consistent rose gold; never add plain "
                "yellow-gold or silver sections."
            )
        else:
            metal_colour_rule = GOLD_COLOR_RULE

        # Framing/orientation rules are FOUNDATION, not optional content: they
        # were previously mixed into the same word-budget list as per-item
        # data (components/stones/material) and silently got trimmed whenever
        # a detailed record filled the 80-word cap first — confirmed live,
        # STRAIGHT_CENTERED_RULE dropped from a ring record with just one
        # component. Foundation is always kept in full; only the optional,
        # data-driven sentences below are subject to the budget.
        foundation = [
            f"Create a clean floating catalogue photograph on solid pure white "
            f"containing {relation} from the reference.",
            "Remove the display stand, holder, tray, hand, tag and background "
            "from the source; only the jewellery remains.",
            "Keep the complete jewellery fully inside the frame, with a "
            "visible plain margin of at least 5% of the image width between "
            "the nearest metal, chain, stone, clasp or dangle and every "
            "edge: left, right, top and bottom.",
            STRAIGHT_CENTERED_RULE,
            metal_colour_rule,
        ]

        optional = []

        silhouette = str(design.get("silhouette") or "").strip(" .")
        if silhouette:
            optional.append(
                f"Preserve each complete photographed {silhouette} silhouette."
            )

        components = []
        for component in design.get("components") or []:
            name = str(component.get("name") or "").strip()
            shape = str(component.get("shape") or "").strip()
            if name:
                components.append(f"{name} ({shape})" if shape else name)
        if components:
            optional.append(
                "Keep the component order: " + ", then ".join(components[:4]) + "."
            )

        for group in (design.get("stone_groups") or [])[:2]:
            count = group.get("count")
            where = str(group.get("where") or "its setting").strip()
            cut = str(group.get("cut") or "").strip()
            colour = str(group.get("colour") or "").strip()
            if count is not None:
                stones = " ".join(x for x in (colour, cut, "stones") if x)
                optional.append(f"Keep exactly {count} {stones} on {where}.")

        metal = str(design.get("metal_colour") or "").strip()
        colours = [str(c).strip() for c in design.get("colours_present") or [] if str(c).strip()]
        material = ", ".join(([metal] if metal else []) + colours[:2])
        if material:
            optional.append(f"Maintain the photographed {material} materials and colours.")

        closing = (
            "Keep the original orientation, proportions, spacing and sharp fine "
            "detail, with even empty white space around the complete jewellery."
        )
        # Cap raised from 80 to 140 to fit the foundation block above (itself
        # ~85 words once the framing/orientation rules were added) plus room
        # for optional data — matching the length range (97-156 words) already
        # proven to work well tonight on real generations, not a guess.
        selected = list(foundation)
        for sentence in optional + [closing]:
            candidate = " ".join(selected + [sentence])
            if len(candidate.split()) <= 140:
                selected.append(sentence)
        prompt = " ".join(selected)
        if len(prompt.split()) >= 30:
            return prompt

    earring_prompt = _klein_short_earring_isolation_prompt(profile)
    if earring_prompt:
        return earring_prompt
    description = profile.meaning or profile.name
    return (
        f"Create a clean floating catalogue image containing the exact "
        f"{description} from the source, centred on solid pure white. Remove "
        f"the display stand, holder, tray, hand, tag and background from the "
        f"source; only the jewellery remains. Keep the complete jewellery "
        f"fully inside the frame, with a visible plain margin of at least 5% "
        f"of the image width between the nearest metal, chain, stone, clasp "
        f"or dangle and every edge: left, right, top and bottom. "
        f"{STRAIGHT_CENTERED_RULE} {GOLD_COLOR_RULE} Preserve "
        f"its photographed piece count, silhouette, topology, materials, colours, "
        f"stones, cut-outs, proportions and orientation. Keep the complete "
        f"ornament visible, sharply focused and unchanged, with even empty white "
        f"space around it."
    )


def build_studio_edit_prompt(
    category: str,
    engine: str = "copilot",
    *,
    include_tag_image: bool = False,
    is_plain_bg: bool = False,
) -> str:
    """Compact, source-explicit prompt for a two-image catalogue edit.

    Both providers perform better when the goal, image roles, preserved
    invariants and allowed change are stated once and without contradictions.
    Gemini additionally needs an explicit image-output instruction because it
    is a multimodal chat model and may otherwise answer with prose.
    """

    from ornament_placement import get_profile, studio_guidance

    normalized_category = (category or "jewellery").lower().strip()
    profile = get_profile(normalized_category)
    cat_label = profile.name
    destination_number = 3 if include_tag_image else 2
    tag_role = (
        "- Image 2: price/tag reference used only to read the item code; never copy it into the photograph.\n"
        if include_tag_image else ""
    )
    label_reply = (
        "\nAfter the image, put the exact code read from Image 2 on one final written-reply line as "
        "`LABEL: <item code>`. This line belongs to the chat reply, never inside the image."
        if include_tag_image else ""
    )
    earring_profiles = {
        "earrings", "jhumka", "tops", "ladies_bali", "mens_bali",
        "bali", "dul",
    }
    if is_plain_bg:
        # A blank white plate has no prop/stand to preserve or attach to —
        # the stand-preservation rules below assume a real scene and would
        # push the model to invent a fake pedestal/hook on empty white,
        # exactly the opposite of a plain e-commerce product shot.
        attachment_rule = (
            "- There is no display prop, stand or holder in Image "
            f"{destination_number} — do not invent one. If it is a pair "
            "(earrings, bangles), keep both pieces equal-sized and aligned, "
            "spaced naturally as a matched set.\n"
        )
    elif profile.key in earring_profiles:
        attachment_rule = (
            f"- EARRING-STAND RULE: if Image {destination_number} contains a T-bar, earring stand, hooks or holes, "
            "preserve the entire stand—base, upright stem, horizontal bar, holes and hooks. "
            "Hang one earring from each existing attachment point so its top is physically "
            "connected and its body dangles below. Never erase the stand or leave the earrings "
            "floating. Scale the pair to the stand's attachment spacing; this natural stand fit "
            "overrides the 75–90% product-fill target.\n"
        )
    else:
        attachment_rule = (
            f"- If Image {destination_number} contains a category-specific holder, hook or stand, preserve it and "
            "attach the ornament to it at realistic scale; never erase it to make room.\n"
        )
    if engine.lower() == "gemini":
        opening = (
            "Generate and return exactly ONE edited photograph. Do not answer "
            "with text and do not describe the edit."
        )
    else:
        opening = "Create exactly ONE edited catalogue photograph."

    if is_plain_bg:
        category_rule_line = f"- CATEGORY PLACEMENT ({cat_label}): centred, e-commerce product-photography style.\n"
        support_surface_block = ""
        plain_bg_line = (
            f"- Image {destination_number} is a plain white/seamless background with no physical props "
            "or surface. Do not invent a pedestal, stand, table or shadow scene. Centre the ornament, "
            "floating naturally, with only a soft, realistic contact shadow directly beneath it — "
            "exactly like a standard e-commerce product photograph.\n"
        )
    else:
        category_rule_line = studio_guidance(normalized_category) + "\n"
        support_surface_block = (
            f"- First inspect Image {destination_number}'s geometry and identify a real, unobstructed support surface large\n"
            "  enough for the complete ornament: a pedestal top, tray/base, table plane or display pad.\n"
            "- Place the jewellery wholly ON one suitable surface with a stable physical resting pose,\n"
            "  correct perspective, a visible contact point and a soft contact shadow directly beneath it.\n"
            "- Respect prop depth and occlusion: the jewellery may sit inside or in front of an object only\n"
            "  when that object's opening and surface can physically contain and support it.\n"
            "- Never balance jewellery on a thin rim or sharp edge; never bridge an opening, cross a lid,\n"
            "  intersect a prop, pass through an object, hang unsupported or float in empty space.\n"
            "- Keep the complete ornament clear of support edges. If no decorative prop has a suitable\n"
            "  surface, use the scene's main ground/table plane instead. Never invent a new pedestal or prop.\n"
        )
        plain_bg_line = ""

    return f"""{opening}

IMAGE ROLES
- Image 1: source photograph of the {cat_label}; this is the design authority.
{tag_role}- Image {destination_number}: destination studio scene and physical display props.

EDIT GOAL
Place a precise photographic cutout of the jewellery from Image 1 into Image {destination_number}.
Remove the background, velvet, holder and display stand FROM IMAGE 1 ONLY.
Never remove, replace, repaint or redesign any object belonging to Image {destination_number}.

PRESERVE EXACTLY
- The complete physical design from Image 1: outline, central motif, component count,
  filigree/openings, links, stones and their positions/colours, prongs, drops and dangles.
- Dark areas inside openwork are holes: make them transparent so Image {destination_number} shows through.
- Image {destination_number}'s crop, scene, physical props, colour and lighting.
- Treat Image {destination_number} as an immutable destination plate. Preserve every destination prop and support,
  including its base, vertical stem, horizontal bar, hooks, holes, edges and original shadows.
  The only permitted pixel changes to Image 2 are natural jewellery occlusion, attachment contact
  and shadow, plus seamless removal of existing rendered text or branding. Empty non-text areas
  of Image 2 must remain unchanged.
Do not redraw, beautify, simplify, replace, add or remove any jewellery component.

COMPOSITION
- Apply the following category rule before choosing a destination support:
{category_rule_line}{support_surface_block}{plain_bg_line}{attachment_rule}- If preserving Image 2 conflicts with jewellery size or framing, preserving Image 2 wins.
- If it is a pair, keep both pieces equal-sized, aligned and close together.
- Match Image {destination_number}'s light and perspective while keeping the metal and stones sharp.

{STUDIO_PROMPT_RULES}
ZERO-TEXT OUTPUT — the finished image must contain no readable characters or graphic branding:
no words, letters, numbers, SKU, caption, badge, signature, logo, brand name, watermark or
AI-attribution label. Do not preserve or reproduce text from either input. Where input text or a
logo exists, reconstruct the underlying background cleanly without changing nearby objects.{label_reply}"""
