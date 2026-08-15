"""
aradhya_realism.py — master prompt kit for the Aradhya brand-ambassador model
library. Single source of truth for FACE_LOCK / PROPORTION_GUARD /
NO_JEWELLERY_RULE / realism language / negatives, so every future Aradhya
generation script imports from here instead of re-declaring its own copy.

Realism language incorporated from two sources: a general AI-photorealism
cheat-sheet (camera/lens/lighting/texture/color/negative trigger words) and a
worked example prompt (feature-by-feature skin/eye/lip/hair breakdown, named
real camera bodies, direction-specific lighting, an AI-artifact-specific
negative list). Both folded in below.
"""

FACE_LOCK = (
    "IMPORTANT: Use the woman in the reference photo (image 1) as the model. "
    "Maintain her exact face, skin tone, and features — she must be immediately "
    "recognizable as the same person. Do NOT use her store uniform."
)

PROPORTION_GUARD = (
    "CRITICAL — BODY PROPORTIONS: the head must be anatomically correct size "
    "relative to the shoulders, chest and body — a normal adult head-to-body "
    "ratio, NOT an oversized head on a narrow frame. Shoulders and body must "
    "read as naturally proportioned, matching the build visible in the "
    "reference photo, not just the face."
)

NO_JEWELLERY_RULE = (
    "STORY CONTEXT — read this first: this is a jewellery catalogue's pre-"
    "shoot reference photo, taken BEFORE hair and makeup styling and BEFORE "
    "any jewellery is put on. The model has deliberately come to set with "
    "bare earlobes, bare neck, bare wrists, bare fingers, bare ankles and a "
    "bare waist — no piercings filled with studs, no chains, no rings, no "
    "bangles, no anklets, no waist belt/kamarbandh, no nose ring/nath, no "
    "hair jewellery or maang tikka, no brooches. The jewellery will be added "
    "digitally in post-production onto this exact photo, so every one of "
    "those areas must show completely plain, unadorned skin — not even a "
    "single stud or thin chain. Treat any jewellery appearing anywhere on "
    "the model as a critical failure of the shot.\n\n"
    "TWO SPECIFIC ITEMS THAT KEEP SLIPPING THROUGH — pay extra attention:\n"
    "1. NOSE: her nose has NO stud, NO ring, NO nath of any size or metal — "
    "the nostril is completely bare, exactly as if she has never had it "
    "pierced. Do not add even a tiny diamond or gold dot on the nose.\n"
    "2. EARS: her earlobes have NO stud, NO small everyday earring, NO hoop "
    "— completely bare earlobes with no piercing jewellery visible at all, "
    "not even a subtle plain stud."
)

# --- Realism block -----------------------------------------------------
# Feature-by-feature breakdown (skin / eyes / lips / hair) rather than one
# generic "realistic skin" line — this is the single biggest lever against
# the "plastic AI face" look.
SKIN_DETAIL = (
    "SKIN & FEATURE REALISM: her skin shows true-to-life texture — visible "
    "pores, faint natural variation in tone, subtle oil sheen on the "
    "forehead and cheekbones where light catches it, tiny natural "
    "imperfections preserved. No beauty retouching, no plastic or airbrushed "
    "skin — true editorial realism. Her eyes are sharp with a natural "
    "catchlight reflecting inside the pupils, fine individual eyelashes, "
    "natural eyebrows with visible hair strands. Lips are soft with "
    "realistic moisture and texture, natural tone, no heavy makeup. Where "
    "hair meets the hairline, preserve tiny flyaway and baby hairs rather "
    "than a perfectly smooth edge — individual hair strands should read as "
    "crisp and naturally lit, not a solid mass."
)

# Camera/lens/lighting/color/grain language from the cheat-sheet, made
# concept-agnostic (per-concept camera/lighting lines still override the
# specific lens/light-direction where a concept calls for something
# different, e.g. dusk/interior lighting).
REALISM_CORE = (
    "PHOTOREALISM: shot as if on a real full-frame DSLR or mirrorless camera "
    "(e.g. Sony A7R), true documentary/editorial photography — not an "
    "illustration, render, or digital painting. Natural, physically-accurate "
    "lighting with realistic shadow falloff and soft highlight roll-off, no "
    "clipped highlights and no crushed blacks. Natural color grading with "
    "true skin tones and a slight warm daylight bias where the scene calls "
    "for it — no oversaturation, no artificial HDR look. Subtle cinematic "
    "film grain and faint sensor noise in the shadows for organic texture. "
    "Shallow depth of field with natural, creamy bokeh separating the model "
    "from the background; the face stays tack-sharp."
)

QUALITY = (
    "This is an UNRETOUCHED, RAW photographic reference — think behind-the-"
    "scenes test Polaroid or a straight-out-of-camera RAW file, NOT a final "
    "retouched fashion-magazine cover or beauty-ad image. Skin must show "
    "real, visible texture; if the skin looks smooth, glossy, or airbrushed "
    "the shot has FAILED regardless of how good everything else looks. "
    f"{REALISM_CORE} {SKIN_DETAIL} "
    "The model looks real, three-dimensional, natural — never airbrushed, "
    "never computer-generated, never like a retouched advertisement. NO "
    "jewellery visible on model anywhere — this is a blank reference shot "
    "for later jewellery compositing. Sharp focus on the model, natural "
    "environmental depth of field."
)

# AI-artifact-specific negatives, beyond the generic "no CGI" — catches the
# failure modes that actually show up in hand/finger-heavy jewellery poses
# (ring/bangle zones) and face-distortion artifacts. Also fights a
# confirmed failure mode: some engines (observed on Copilot/Designer)
# default to glossy, beauty-retouched skin even when the QUALITY block
# explicitly asks for texture — repeating the anti-retouch instruction here
# as an explicit negative measurably helps beyond stating it once.
NEGATIVE = (
    "AVOID: cartoon style, anime, CGI, 3D render, game-engine look, plastic "
    "or waxy skin, over-smoothing, smooth/glossy/poreless skin, beauty-"
    "magazine retouching, skin-smoothing filter, Facetune/Instagram-face-"
    "tune look, glossy commercial-ad skin, artificial glow, fake bokeh, "
    "distorted face, warped or asymmetric eyes, extra or malformed fingers, "
    "fused fingers, any text, any brand name or logo, any watermark of any "
    "kind — this is a blank pre-production reference photo with absolutely "
    "no branding of any kind on it, not even the studio's own. Visible skin "
    "texture (pores, subtle unevenness) is REQUIRED, not optional."
)


IVORY_GOLD_SAPPHIRE_PALETTE = (
    "BACKDROP PALETTE — strict for the SETTING only: the backdrop, "
    "environment, walls, and any floral/prop accents in this shoot must stay "
    "within ivory/cream, gold/champagne, and a rich, deep sapphire-cobalt "
    "blue (like a cobalt sapphire gemstone, hex approx #23519D — saturated "
    "royal blue, NOT pale/dusty, NOT black-navy). This backdrop restriction "
    "does NOT apply to her outfit — style her outfit in whatever rich, "
    "vivid, saturated color best suits this specific concept (the outfit "
    "color is specified separately below and should be followed exactly, "
    "even where it differs from the backdrop tones)."
)


def build_prompt(label, location, outfit, pose, camera, extra_negative="", palette=None):
    """Assemble a full Aradhya generation prompt from concept pieces, with
    NO_JEWELLERY_RULE stated up top (primacy) and restated as a reminder near
    the end, matching the structure that measurably reduced jewellery
    leakage in earlier testing."""
    negative = NEGATIVE
    if extra_negative:
        negative = f"{NEGATIVE} {extra_negative}"
    palette_block = f"{palette}\n\n" if palette else ""
    return (
        f"ARADHANA JEWELLERS — Creative Model Photoshoot Reference (Concept: {label})\n\n"
        f"{NO_JEWELLERY_RULE}\n\n"
        f"{FACE_LOCK}\n\n"
        f"{palette_block}"
        f"LOCATION / ENVIRONMENT:\n{location}\n\n"
        f"OUTFIT:\nStyle her in {outfit}.\n\n"
        f"POSE & HERO ZONE:\n{pose}\n\n"
        f"{PROPORTION_GUARD}\n\n"
        f"CAMERA: {camera}\n\n"
        f"QUALITY:\n{QUALITY}\n\n"
        f"NEGATIVE PROMPT:\n{negative}\n\n"
        f"REMINDER: {NO_JEWELLERY_RULE}\n\n"
        f"Generate a high-quality image matching these exact specifications."
    )
