"""
Aradhana Jewellers — Professional Catalogue Model Engine
Generates lifestyle/model images using the Codex engine.
Full template library, model roster, camera specs, and lighting language.
"""
import aradhya_realism as ar

# ── MODEL LIBRARY ─────────────────────────────────────────────────────────────

MODELS = {
    # Women
    "F1": "A beautiful contemporary Indian woman in her late 20s, refined luxury aesthetic, "
          "subtle Western-fusion styling, flawless natural skin, minimal makeup, confident expression",
    "F2": "A beautiful Indian woman in her late 20s to early 30s, traditional festive styling, "
          "silk saree or salwar kameez, warm expressive features, traditional grace",
    "F3": "A stunning Indian bride, early to mid 20s, full bridal makeup and styling, "
          "bridal red or pastel lehenga, glowing skin, wedding-ready look",
    "F4": "An elegant mature Indian woman in her early 40s, sophisticated presence, "
          "premium saree or formal attire, graceful and distinguished",

    # Men
    "M1": "A handsome contemporary Indian man in his early 30s, luxury lifestyle aesthetic, "
          "smart-casual or formal Western attire, clean grooming, confident",
    "M2": "A handsome Indian man in his early 30s, traditional festive styling, "
          "kurta or sherwani, warm expressive features",
    "M3": "A distinguished mature Indian man in his mid 40s, premium business or formal attire, "
          "authoritative and polished presence",

    # Kids
    "KG": "An adorable Indian girl aged 6-8, bright natural smile, "
          "traditional or festive dress, playful yet graceful",
    "KB": "An adorable Indian boy aged 6-8, bright natural smile, "
          "kurta or smart casual wear, lively natural expression",
}

# ── LIGHTING LANGUAGE (consistent across all shots) ───────────────────────────

LIGHTING = (
    "Soft diffused luxury studio lighting. Neutral cream or warm grey background. "
    "Real, visible skin texture — not retouched, not airbrushed. Minimal clean makeup. "
    "The jewellery must be the brightest, sharpest, most detailed element in the frame — "
    "it is the absolute hero of the shot."
)

# ── CAMERA SPECS BY BODY ZONE ─────────────────────────────────────────────────

CAMERA = {
    "face":   "85–135mm portrait lens, shallow depth of field, face and jewellery in sharp focus",
    "neck":   "70–100mm, chest-up framing, neck and jewellery as focal point",
    "hand":   "100mm macro-style framing, crisp detail on fingers and jewellery",
    "wrist":  "100mm macro-style framing, wrist detail, jewellery in sharp focus",
    "upper_arm": "85–100mm portrait detail, shoulder-to-elbow crop with the upper arm and armlet fully visible",
    "waist":  "mid-body crop emphasizing the waistline and jewellery",
    "feet":   "lower-leg close-up, elegant foot positioning, jewellery as focal point",
    "bridal": "85mm portrait, face and full jewellery visible, soft bokeh background",
}

# ── CATEGORY TEMPLATE LIBRARY ─────────────────────────────────────────────────
# Each category has: model, zone, and 3 templates

CATEGORY_TEMPLATES = {

    "necklace": {
        "models": ["F1", "F2"],
        "zone": "neck",
        "templates": [
            "front portrait, model facing camera directly, necklace centred on chest, full neck and collarbone visible",
            "45-degree portrait, model turned slightly to one side, necklace falling naturally, elegant three-quarter angle",
            "half-body editorial, model in composed pose, necklace as centrepiece, upper body styling visible",
        ]
    },

    "mangalsutra_long": {
        "models": ["F2", "F3", "F4"],
        "zone": "neck",
        "templates": [
            "waist-up traditional pose, married woman, mangalsutra draping naturally, graceful dignified expression",
            "three-quarter portrait, mangalsutra visible from neckline, authentic traditional styling",
            "walking pose, candid editorial feel, mangalsutra in motion, beautiful lifestyle moment",
        ]
    },

    "ladies_chains": {
        "models": ["F1", "F2"],
        "zone": "neck",
        "templates": [
            "female neckline close-up, chain resting elegantly on collarbone, soft focus background",
            "half-body portrait, chain layered naturally, contemporary styling",
            "lifestyle portrait, model in natural setting, chain as subtle statement piece",
        ]
    },

    "gents_chains": {
        "models": ["M1", "M2"],
        "zone": "neck",
        "templates": [
            "male neckline, open collar shirt or kurta, chain visible on chest, masculine and confident",
            "three-quarter portrait, chain as style accent, smart casual or formal styling",
            "lifestyle hand/chest pose, chain as premium detail, editorial masculine aesthetic",
        ]
    },

    "mangalsutra_short": {
        "models": ["F3", "F4"],
        "zone": "neck",
        "templates": [
            "married woman portrait, front-facing, mangalsutra at neckline, warm and graceful expression",
            "half-body, saree or lehenga styling, mangalsutra visible and prominent",
            "close neckline crop, mangalsutra as focal point, soft bokeh",
        ]
    },

    "necklace": {
        "models": ["F1", "F2"],
        "zone": "neck",
        "templates": [
            "front portrait, necklace centred and prominent, model looking directly at camera",
            "45-degree portrait, necklace draped elegantly at angle",
            "half-body editorial, full styling visible, necklace as hero piece",
        ]
    },

    "pendant": {
        "models": ["F1", "F2"],
        "zone": "neck",
        "templates": [
            "neck crop close-up, pendant centred on collarbone, delicate and precise",
            "half-body, pendant visible as accent piece, contemporary styling",
            "layered styling, pendant worn with chain, lifestyle editorial look",
        ]
    },

    "locket": {
        "models": ["F1", "F2", "F4"],
        "zone": "neck",
        "templates": [
            "neck crop, locket as focal point, elegant and meaningful",
            "half-body, locket resting on chest, traditional or contemporary styling",
            "lifestyle portrait, locket as personal statement piece",
        ]
    },

    "choker": {
        "models": ["F1", "F2", "F3"],
        "zone": "neck",
        "templates": [
            "tight neck close-up, choker sitting perfectly on neck, ultra-sharp detail",
            "side portrait, choker visible at neck, elegant profile",
            "elegant seated pose, choker as statement piece, composed editorial",
        ]
    },

    "earrings": {
        "models": ["F1", "F2", "F3"],
        "zone": "face",
        "templates": [
            "front face portrait, both earrings visible, model facing camera, 85mm shallow depth of field",
            "45-degree profile, near earring in sharp focus, face turned gracefully",
            "side profile with hair tucked back, earring fully revealed, clean elegant composition",
        ]
    },

    "tops": {
        "models": ["F1", "F2"],
        "zone": "face",
        "templates": [
            "front face close-up, ear and top visible, minimal jewellery detail crisp",
            "45-degree face, earring delicate and precise in frame",
            "side profile, hair swept back, earring as sole focal point",
        ]
    },

    "ladies_bali": {
        "models": ["F1", "F2", "F3"],
        "zone": "face",
        "templates": [
            "front face, bali earrings on both ears, warm expressive face",
            "45-degree portrait, one bali in sharp focus, graceful profile",
            "side profile with hair tucked, bali earring as hero, elegant neck line visible",
        ]
    },

    "mens_bali": {
        "models": ["M1", "M2"],
        "zone": "face",
        "templates": [
            "front masculine portrait, bali earring visible, confident styling",
            "45-degree profile, earring in sharp focus, masculine and refined",
            "side profile, bali as subtle statement, contemporary male editorial",
        ]
    },

    "maang_tika": {
        "models": ["F3", "F2"],
        "zone": "bridal",
        "templates": [
            "front bridal portrait, maang tika centred on forehead, full bridal makeup and styling visible",
            "head slightly lowered, maang tika falling naturally, soft and beautiful angle",
            "45-degree bridal profile, maang tika visible, face turned gracefully, full jewellery styling",
        ]
    },

    "nath": {
        "models": ["F3", "F2"],
        "zone": "face",
        "templates": [
            "front close-up face, nath (nose ring) as focal point, bridal or festive styling",
            "45-degree face turn, nath profile visible, soft depth of field",
            "side profile, nath visible from the side, elegant bridal pose",
        ]
    },

    "ladies_rings": {
        "models": ["F1", "F2"],
        "zone": "hand",
        "templates": [
            "single elegant female hand, ring prominently displayed on finger, soft focus background",
            "both hands together, rings on complementary fingers, graceful feminine pose",
            "ring close-up on fingers, macro detail, beautiful manicured hand",
        ]
    },

    "gents_rings": {
        "models": ["M1", "M2", "M3"],
        "zone": "hand",
        "templates": [
            "masculine hand, ring on finger, confident masculine styling, strong hand pose",
            "hand with shirt or suit cuff visible, ring as power accessory",
            "lifestyle hand pose, ring as part of refined grooming, premium aesthetic",
        ]
    },

    "bangles": {
        "models": ["F1", "F2", "F3"],
        "zone": "wrist",
        "templates": [
            "single wrist raised elegantly, bangles stacked beautifully, warm skin tone contrast",
            "both hands together, bangles on both wrists, traditional festive pose",
            "raised wrist pose, bangles catching light, beautiful movement and detail",
        ]
    },

    "ladies_bracelet": {
        "models": ["F1", "F2"],
        "zone": "wrist",
        "templates": [
            "female wrist close-up, bracelet as elegant accent, clean composition",
            "hand and wrist in natural pose, bracelet draping beautifully",
            "crossed arms or wrist detail, bracelet as statement piece",
        ]
    },

    "gents_bracelet": {
        "models": ["M1", "M3"],
        "zone": "wrist",
        "templates": [
            "male wrist, bracelet on masculine forearm, confident styling",
            "wrist with watch or cuff, bracelet as complementary piece",
            "crossed arms lifestyle pose, bracelet as subtle luxury detail",
        ]
    },

    "ladies_kada": {
        "models": ["F1", "F2", "F4"],
        "zone": "wrist",
        "templates": [
            "wrist close-up, kada as bold statement piece, feminine wrist",
            "both wrists visible, kada styling, traditional elegance",
            "raised wrist pose, kada catching studio light",
        ]
    },

    "gents_kada": {
        "models": ["M1", "M2", "M3"],
        "zone": "wrist",
        "templates": [
            "wrist close-up, kada on masculine wrist, powerful and premium",
            "folded arms pose, kada visible on forearm, confident stance",
            "lifestyle wrist pose, kada as signature piece, editorial masculine look",
        ]
    },

    "waist_belt": {
        "models": ["F2", "F3"],
        "zone": "waist",
        "templates": [
            "waist crop, kamarbandh/waist belt as centrepiece, saree or lehenga styling",
            "three-quarter body, full waist jewellery visible in context of bridal/festive outfit",
            "bridal pose, waist belt as part of complete bridal ensemble",
        ]
    },

    "payal": {
        "models": ["F1", "F2", "F3"],
        "zone": "feet",
        "templates": [
            "standing feet close-up, anklets on both feet, elegant foot positioning on marble or wooden floor",
            "walking pose, anklets in gentle motion, lifestyle candid feel",
            "seated feet detail, anklets draped beautifully, soft floral or fabric background",
        ]
    },

    "wati": {
        "models": ["F2", "F3"],
        "zone": "neck",
        "templates": [
            "front neckline close-up, Maharashtrian Wati mangalsutra centred and fully visible",
            "three-quarter traditional portrait, Wati cups and black-bead chain clearly visible",
            "chest-up festive portrait, Wati mangalsutra at natural worn length",
        ]
    },

    "diamond": {
        "models": ["F1"],
        "zone": "face",
        "templates": [
            "glamorous front portrait, diamond jewellery as ultimate luxury statement, high-fashion editorial",
            "45-degree glamour pose, diamond catching light, sophisticated and striking",
            "side profile, diamond jewellery in cinematic close-up, luxury lifestyle aesthetic",
        ]
    },

    "silver": {
        "models": ["F1", "F2"],
        "zone": "neck",
        "templates": [
            "contemporary styling, silver jewellery as clean modern statement",
            "traditional festive look, silver complementing ethnic outfit",
            "lifestyle portrait, silver jewellery in natural setting",
        ]
    },
}

# Default for unknown categories
DEFAULT_TEMPLATE = {
    "models": ["F1", "F2"],
    "zone": "neck",
    "templates": [
        "front portrait, jewellery prominently displayed, elegant model",
        "45-degree portrait, jewellery as focal point, graceful angle",
        "half-body editorial, jewellery styled as hero piece",
    ]
}


def get_templates(category: str) -> dict:
    """Get the full template config for a category."""
    from ornament_placement import get_profile

    # Normalize category name and resolve stock labels/purity suffixes through
    # the shared Indian-ornament taxonomy before using legacy substring logic.
    cat = category.lower().strip()
    profile = get_profile(cat)
    source = None
    if profile.key in CATEGORY_TEMPLATES:
        source = CATEGORY_TEMPLATES[profile.key]
    elif cat in CATEGORY_TEMPLATES:
        # Material catch-alls (silver/diamond) remain direct legacy entries;
        # their physical form must still be inferred from Image 1 in prompt.
        source = CATEGORY_TEMPLATES[cat]
    elif profile.template_key in CATEGORY_TEMPLATES:
        source = CATEGORY_TEMPLATES[profile.template_key]
    if source is not None:
        result = {
            "models": list(source["models"]),
            "zone": source["zone"],
            "templates": list(source["templates"]),
        }
        if profile.model_codes:
            result["models"] = list(profile.model_codes)
        if profile.zone:
            result["zone"] = profile.zone
        return result

    # Researched stock-only categories such as Bajuband do not yet have a
    # bespoke pose library.  Keep the neutral composition templates, but do
    # not lose their verified anatomy or wearer while waiting for assets.
    if profile.key != "generic" and (profile.zone or profile.model_codes):
        result = {
            "models": list(profile.model_codes or DEFAULT_TEMPLATE["models"]),
            "zone": profile.zone or DEFAULT_TEMPLATE["zone"],
            "templates": list(DEFAULT_TEMPLATE["templates"]),
        }
        return result

    # Never use substring matching here.  It routed the literal category
    # "ring" to "earrings" because "ring" is a substring of "earrings",
    # selecting a face pose instead of a hand pose.  Unknown free-form values
    # use the neutral default; every supported stock label resolves above.
    return DEFAULT_TEMPLATE


def _landmark_anchor_instruction(zone: str, model_image_path: str) -> str:
    """Deterministic pixel/fractional attachment anchor computed locally from
    MediaPipe landmarks, instead of leaving position AND scale entirely to
    the generative model's own visual guess. Returns "" when the zone has no
    landmark support yet or detection fails — the existing text guidance
    below still applies either way, so this is additive, not a dependency."""
    if not model_image_path:
        return ""
    try:
        import anatomical_landmarks as _al
        anchor = _al.anchor_for_zone(zone, model_image_path)
    except Exception:
        return ""
    if not anchor.get("ok"):
        return ""

    fx, fy = anchor["point_frac"]
    if zone == "face":
        return (
            f"\nMEASURED ANCHOR (computed from this exact photo, not a guess): "
            f"the visible ear's attachment point sits at fractional image "
            f"coordinate ({fx}, {fy}) — that is {int(fx*100)}% across and "
            f"{int(fy*100)}% down the frame. Attach the top of the ornament "
            f"there. Measured face height is {anchor['face_height_px']:.0f}px; "
            f"size the ornament using that as your physical ruler, not frame "
            f"space or guesswork.\n"
        )
    if zone == "hand":
        return (
            f"\nMEASURED ANCHOR (computed from this exact photo, not a guess): "
            f"the target finger joint sits at fractional image coordinate "
            f"({fx}, {fy}) — {int(fx*100)}% across and {int(fy*100)}% down the "
            f"frame. Measured finger width is {anchor['finger_width_px']:.0f}px "
            f"and wrist width is {anchor['wrist_width_px']:.0f}px; size the "
            f"ring/bangle band opening from those measurements, not a guess.\n"
        )
    # neck/wrist/upper_arm/waist/feet all come from pose_anchor(), which
    # returns the same {point_frac, reference_px} shape regardless of zone —
    # one generic message covers all five instead of repeating near-identical
    # text per zone.
    zone_ruler_label = {
        "neck": "shoulder span (collarbone to collarbone)",
        "wrist": "forearm length (elbow to wrist)",
        "upper_arm": "upper-arm length (shoulder to elbow)",
        "waist": "hip span (hip to hip)",
        "feet": "shin length (knee to ankle)",
    }.get(zone)
    if zone_ruler_label and "reference_px" in anchor:
        return (
            f"\nMEASURED ANCHOR (computed from this exact photo, not a guess): "
            f"the {zone} attachment point sits at fractional image coordinate "
            f"({fx}, {fy}) — {int(fx*100)}% across and {int(fy*100)}% down the "
            f"frame. Measured {zone_ruler_label} is {anchor['reference_px']:.0f}px "
            f"in this photo; size and scale the ornament using that as your "
            f"physical ruler, not frame space or guesswork.\n"
        )
    return ""


def _hole_map_instruction(jewel_image_path: str) -> str:
    """Measured, per-photo hole-vs-enamel classification instead of leaving
    that judgement to the generative model — a real, repeated failure this
    session (TP22_138, 2026-08-02) was filling genuine hollow lattice gaps
    in with solid black, mistaking them for enamel. hole_detection.py
    settles this deterministically per photo (flood-fill from the image
    border: a hollow gap is the same velvet material as the connected
    background; real enamel measurably isn't). Returns "" on any failure —
    additive, not a dependency; the OPENWORK-VS-ENAMEL text rule still
    applies as the fallback when this can't run."""
    if not jewel_image_path:
        return ""
    try:
        import hole_detection as _hd
        result = _hd.classify_dark_regions(jewel_image_path)
    except Exception:
        return ""
    if not result.get("ok"):
        return ""

    holes = [r for r in result["regions"] if r["classification"] == "hole" and r["px_count"] > 1500]
    enamel = [r for r in result["regions"] if r["classification"] == "enamel" and r["px_count"] > 1500]
    if not holes and not enamel:
        return ""

    lines = []
    if holes:
        lines.append(
            f"- {len(holes)} region(s) measured as HOLLOW GAPS (same material as the "
            f"velvet background, just enclosed by metal) — these must be transparent/"
            f"see-through in the output, never filled with solid black."
        )
    if enamel:
        lines.append(
            f"- {len(enamel)} region(s) measured as genuine coloured material (not "
            f"background) — preserve these as actual colour, not as holes."
        )
    return (
        "\nMEASURED HOLE MAP (computed from this exact photo, not a guess):\n"
        + "\n".join(lines) + "\n"
    )


def _size_reference_instruction(jewel_image_path: str) -> str:
    """Real-world size, pre-computed by size_reference_service.py's
    background scan (tag-based photogrammetry, cross-checked against a web
    search for the style's typical published size — see that module for why
    neither signal alone is trusted). Looks up a CACHED result only; this
    must never trigger a live computation on the generation hot path (the
    background scanner already ran the Gemini localization call and web
    search once per item, ahead of time). Returns "" when no cached
    reference exists yet or its confidence was flagged low — the existing
    landmark-anchor scale guidance still applies as the fallback either way."""
    if not jewel_image_path:
        return ""
    try:
        import size_reference_service as _srs
        ref = _srs.get_reference(jewel_image_path)
    except Exception:
        return ""
    if not ref.get("ok") or ref.get("strong_candidate_mm") is None:
        return ""

    size_mm = ref["strong_candidate_mm"]
    return (
        f"\nMEASURED REAL-WORLD SIZE (pre-computed, not a guess): this exact piece's "
        f"longest dimension measures approximately {size_mm:.0f}mm ({size_mm/10:.1f}cm), "
        f"confidence: {ref.get('confidence', 'unknown')}. Use this as the physical size "
        f"ceiling when scaling the ornament on the model — do not enlarge it beyond a "
        f"realistic worn size just to make it more visible in frame.\n"
    )


def _build_model_prompt_compact(cat_label: str, zone: str, category_rule: str,
                                anatomical_fit: str, model_image_path: str,
                                jewel_image_path: str) -> str:
    """Condensed model-shoot prompt for Copilot only (2026-08-02).

    Copilot's web composer has a much tighter character ceiling than
    Gemini's (reported ~4,000 chars vs Gemini's tens of thousands) — the
    full build_model_prompt() output is ~6,700 characters, comfortably
    past that ceiling, so Copilot was very likely silently truncating it
    mid-instruction with no error. This keeps every rule that traces back
    to a real observed failure (count-exact, openwork-vs-enamel, colour-
    exact, measured hole map, measured size ceiling, sharper-than-frame)
    while dropping restated framing/rationale text, targeting well under
    3,500 characters including the worst-case dynamic inserts (hole map +
    size reference + landmark anchor all firing at once measured at
    ~3,100 chars total).

    Deliberately excludes anything phrased as the model checking or
    verifying its own output (e.g. "check this before returning it") —
    a single-shot image model cannot actually inspect its own result
    after generating, so that framing described a pipeline-side quality
    gate, not a real generation instruction, and doesn't belong here."""
    hole_map = _hole_map_instruction(jewel_image_path)
    size_ref = _size_reference_instruction(jewel_image_path)
    landmark = _landmark_anchor_instruction(zone, model_image_path)

    return f"""Create exactly ONE edited lifestyle catalogue photograph.

IMAGES: 1) source {cat_label} jewellery — the exact design to use. 2) model reference photo — the exact person, pose, outfit and background to edit in place. 3) studio background — ignore it for this photo.

TASK: Edit image 2 so its person wears the jewellery from image 1 at the {zone}. Keep every pixel of image 2 outside the jewellery/contact area unchanged: face, body proportions, skin, hair, outfit, background and crop — no stretching, warping or resizing of any body part. This is an edit of image 2, not a new scene or a jewellery redesign.

JEWELLERY ACCURACY:
- Reproduce every dangling element, link, bead, tassel and repeating motif from image 1 at its full count and length — no shortened chain, no missing disc, tassel or bell.
- Image 1 was shot on black velvet. Dark gaps inside open filigree are hollow — the velvet showing through, not black metal or enamel — and must render transparent/see-through on the model. Only a bordered or painted panel is real black enamel; preserve that as an actual colour.{hole_map}{size_ref}
- Preserve every distinct colour and material separately from shape: gold tone, enamel colour, stone colour, matte vs polished finish. Do not flatten, substitute or simplify any of it.
- Render the jewellery sharper and more detailed than anything else in frame.

PLACEMENT:{landmark}
{category_rule}
Fit the jewellery anatomically at the {zone}, touching its real attachment point. Scale it from image 1's true proportions calibrated against image 2's visible anatomy — never resize it for frame space or prominence. {anatomical_fit} Keep parts that pass behind the body naturally hidden, and match the scene's light, perspective and contact shadow.

OUTPUT: Square 1:1, centred crop, jewellery and its attachment point fully visible, nothing touching the frame edge. No text, watermark, logo, signature, caption or AI-attribution label anywhere in the image."""


def build_model_prompt(category: str, job_id: str, variant: int,
                       model_override: str = None,
                       engine: str = "copilot",
                       model_image_path: str = None,
                       jewel_image_path: str = None) -> str:
    """
    Build a complete Codex prompt for a model/lifestyle shot.
    variant: 1, 2, or 3
    """
    from jewellery_image_policy import MODEL_PROMPT_RULES
    from ornament_placement import get_profile, model_guidance

    cfg       = get_templates(category)
    profile   = get_profile(category)
    # Preserve established internal labels in prompts/tests while using the
    # researched business name for stock labels and aliases.
    raw_category = category.lower().strip()
    cat_label = (
        category.replace("_", " ").title()
        if raw_category in CATEGORY_TEMPLATES or profile.key == "material"
        else profile.name
    )
    zone      = cfg["zone"]
    template  = cfg["templates"][(variant - 1) % len(cfg["templates"])]

    # Pick model
    model_key = model_override or cfg["models"][0]
    model_desc = MODELS.get(model_key, MODELS["F1"])
    camera_spec = CAMERA.get(zone, CAMERA["neck"])
    anatomical_fit = {
        "hand": (
            "For a ring, size the band opening to the chosen finger's actual width so the band "
            "wraps that one finger. Keep the crown/motif proportional to that finger and to the "
            "ring in Image 1; it must not cover neighbouring fingers or look miniature."
        ),
        "wrist": (
            "For a bangle or bracelet, match its inner circumference to the visible wrist, with "
            "natural small clearance and no embedding, squeezing or oversized hoop."
        ),
        "upper_arm": (
            "For a bajuband/armlet, fit its circumference around the upper arm between shoulder "
            "and elbow. Follow the arm contour with natural clearance; never move it to the wrist."
        ),
        "face": (
            "For earrings, tops, bali or nath, match scale to the visible earlobe or nose and the "
            "reference ornament; attach at the exact piercing point without covering an implausible "
            "portion of the face or becoming too small to match Image 1."
        ),
        "neck": (
            "For a necklace, chain, pendant, locket or choker, scale its length and width to the "
            "model's neck, collarbone and chest. Follow the body's contour and preserve the source "
            "ornament's natural proportions; never turn a delicate piece into an oversized one."
        ),
        "waist": (
            "For waist jewellery, fit its circumference to the model's waist and follow the body "
            "contour without floating, embedding or changing the ornament's natural proportions."
        ),
        "feet": (
            "For anklets or toe jewellery, fit the actual ankle or toe dimensions and attachment "
            "point without floating, squeezing or enlargement for visibility."
        ),
        "bridal": (
            "Fit the ornament to its exact anatomical attachment points and scale it relative to "
            "the model's forehead, hairline, ears, neck or face as applicable."
        ),
    }.get(zone, "Scale the ornament to the exact body part where it is worn.")

    if engine.lower() == "copilot":
        return _build_model_prompt_compact(
            cat_label, zone, model_guidance(category), anatomical_fit,
            model_image_path, jewel_image_path,
        )

    opening = (
        "Generate and return exactly ONE edited photograph. Do not answer with text."
        if engine.lower() == "gemini"
        else "Create exactly ONE edited lifestyle catalogue photograph."
    )
    return f"""{opening}

IMAGE ROLES
- Image 1: source {cat_label} ornament; this is the exact design authority.
- Image 2: model reference and complete photograph to edit in place. Preserve this person's identity,
  body, skin, hair, outfit, pose, crop, lighting, props AND ORIGINAL BACKGROUND pixel-faithfully.
- Image 3: studio-product background supplied by the pipeline for another output. IGNORE IT for
  this model photograph. Do not move the person into Image 3 and do not copy any part of Image 3.

EDIT GOAL
Edit Image 2 in place so its existing person wears the exact ornament from Image 1 at the
{zone}. The only allowed visual addition is the ornament plus its necessary contact shadow
and occlusion. This is an image edit, not a new scene and not a jewellery redesign.

PRESERVE EXACTLY
- Ornament geometry and construction: outline, central motif, component count, openings,
  filigree, links, stones and positions/colours, prongs, drops, dangles and band/chain pattern.
- Every model-photo pixel outside the minimal jewellery/contact area from Image 2: identity,
  anatomy, pose, natural skin texture, hair, clothing, original background, crop and props.

COUNT-EXACT REQUIREMENT (silent step, do not skip)
Before drawing anything, enumerate every distinct dangling element, chain segment, link,
bead, tassel and repeating motif unit visible in Image 1 — for example "top stud, one
filigree disc, one chain length, one bell/tassel drop" per earring. The finished ornament
must reproduce that exact count, sequence and relative dangle length, worn end to worn end.
A shorter chain, a missing disc, tassel or bell, or any fewer repeating units than Image 1
shows is a FAILED edit even when the overall silhouette looks similar at a glance — this is
the single most common way this edit goes wrong, so treat it as the first thing to check
in your own output before returning it.

OPENWORK-VS-ENAMEL DISTINCTION (check this before COLOR-EXACT below)
Image 1 was photographed on a black velvet backdrop. Any dark area you see INSIDE the metal
outline is one of two different things, and confusing them is a common, serious error:
- If the dark area is bounded by open latticework/filigree with no visible enamel rim or
  fill texture, it is a HOLLOW GAP where the velvet backdrop shows through — not black metal,
  not black enamel. In the finished photograph that gap must show whatever is naturally behind
  it on the model (skin, hair, background) — never fill it in as solid black.
- Only if the dark area has a distinct enamel rim, a filled painted look, or sits flush behind
  a motif as a solid backing panel (not an open lattice) is it real black enamel — preserve
  that as an actual colour, per COLOR-EXACT below.
When uncertain which one you're looking at, treat it as a hollow gap, since filling a real
hollow opening with solid black is the more common and more visible mistake.
{_hole_map_instruction(jewel_image_path)}{_size_reference_instruction(jewel_image_path)}
COLOR-EXACT REQUIREMENT (silent step, do not skip)
Before drawing anything, also enumerate every distinct colour and material surface in Image 1
separately from its shape — for example "yellow-gold metal, black enamel backing behind the
motif, matte-finish petals, one red cabochon stone" — applying the openwork-vs-enamel
distinction above first. Enamel backing, stone colour, and any matte-vs-polished contrast are
real design elements, not shading choices you may simplify away or substitute with plain gold.
If Image 1 shows a genuine coloured enamel panel (not a hollow gap) behind or around a motif,
the finished ornament must show that exact panel and colour, not bare metal and not a solid
black fill where the gap should be transparent. Losing an enamel colour, flattening a two-tone
finish to one tone, or changing a stone's colour is a FAILED edit exactly like a missing dangle
is — check for this separately, because it is easy
to get the count and silhouette right while still failing here.

PLACEMENT
{_landmark_anchor_instruction(zone, model_image_path)}- Apply this category-specific wearing rule before the general scale rules:
{model_guidance(category)}
- Fit the ornament anatomically at the {zone}, touching the correct body attachment point.
- Infer physical scale from the complete ornament in Image 1, then calibrate it against the
  visible anatomy in Image 2. Do not size it according to frame space or desired prominence.
- {anatomical_fit}
- Use realistic worn size: neither oversized nor undersized. When uncertain, prefer the most
  physically plausible conservative scale rather than enlarging the ornament for visibility.
- For ear jewellery, use the visible ear as the physical ruler: the attachment starts exactly
  at the lobe piercing; a normal drop should remain within roughly one ear-height below the
  lobe and its top motif should not dwarf the ear. Exceed that only when Image 1 unmistakably
  shows a genuinely long statement design. Never enlarge earrings merely to make them prominent.
- Preserve perspective and body occlusion: bands/links that pass behind the body part must be
  naturally hidden, while visible parts remain connected. Never let the ornament float.
- Match the model scene's light, perspective, contact shadow and occlusion while keeping the
  ornament sharp. Do not redraw, simplify, beautify or substitute any ornament component.

{MODEL_PROMPT_RULES}
ZERO-TEXT OUTPUT — the finished image must contain no readable characters or graphic branding:
no words, letters, numbers, SKU, caption, badge, signature, logo, brand name, watermark or
AI-attribution label. Do not preserve or reproduce text from any input. Where input text or a
logo exists, reconstruct the underlying background cleanly without changing the person,
jewellery or nearby physical objects."""


def get_model_for_category(category: str, index: int = 0) -> str:
    """Return the preferred model key for a category."""
    cfg    = get_templates(category)
    models = cfg["models"]
    return models[index % len(models)]
