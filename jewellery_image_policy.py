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


# Klein (FLUX.2 Klein Space) is end-of-life — this deployment is Azure
# FLUX.2 Pro only (see tools/azure_flux2_guarded.py). All Klein-specific
# prompt builders were removed here; build_studio_edit_prompt below
# predates Klein too and is being reassessed separately.


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
