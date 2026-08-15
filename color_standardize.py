"""Nudge every delivered catalogue image's gold metal toward one fixed
target average tone, via a per-channel multiplicative gain -- not a
per-pixel colour replacement. This preserves 100% of the source image's
natural specular highlights, shine and local contrast (every pixel keeps
its relative brightness/colour ratio to its neighbours); only the overall
colour balance shifts.

An earlier version of this remapped every gold pixel's colour based purely
on its own brightness percentile (shadow/mid/highlight anchors). That gave
near-identical hex values across items but visibly flattened the metal --
it killed the fine specular detail and shine, because pixel colour was
being replaced outright rather than corrected. Do not go back to that
per-pixel replacement approach; multiplicative gain is the fix for
"looks flat" while still tightening cross-item colour consistency.

Needed because FLUX.2 is not deterministic run-to-run: even with an
identical prompt and explicit target hex values, two generations of the
same design land at visibly different average gold tones. Prompt wording
alone cannot guarantee identical output across a large batch.

Safe in this context specifically because delivered images are on a plain
white/near-white background with no other warm-toned objects (wood, skin,
props) that a hue-based mask could misclassify -- see
local_catalogue_finish.normalize_gold_tone's disabled LAB-space attempt for
what goes wrong once a real scene background is in frame. Do not reuse this
mask against composed-background images without re-verifying it the same
way this was verified (render the mask, look at it, don't assume).
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

# Real gold never renders darker than the shadow target's own floor (~R=161
# in #A14F0E); anything darker within the product is a reflection artifact
# of the black velvet capture stand showing through a polished facet or flat
# band, not real shading. Confirmed no earring/jhumka item in this catalogue
# carries a real black/dark gemstone that could be mistaken for this -- if
# that ever changes for another category, re-verify before reusing this on
# it (a real dark stone would be a similarly compact dark blob and could be
# inpainted away just as easily).
REFLECTION_ARTIFACT_MAX_CHANNEL = 110


def remove_reflection_artifacts(img: Image.Image) -> Image.Image:
    arr = np.array(img.convert("RGB"))
    maxc = arr.max(axis=-1)
    mask = (maxc < REFLECTION_ARTIFACT_MAX_CHANNEL).astype(np.uint8) * 255
    if not mask.any():
        return img
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    inpainted = cv2.inpaint(bgr, mask, inpaintRadius=6, flags=cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB))

# Locked-in target average gold tone (hex / RGB) -- the mid-tone anchor from
# the approved prompt palette, darkened per owner feedback. Must stay in
# sync with the RGB values stated in config/flux2_pro_catalogue_prompt.txt.
TARGET_RGB = (195, 155, 71)  # #C39B47

# Clamp how far any single channel's gain can push -- keeps a badly-off
# generation from being over-corrected into an unnatural colour, and
# guarantees this never behaves like the old LAB attempt (unbounded shift).
MIN_GAIN = 0.75
MAX_GAIN = 1.35


def gold_mask(img: Image.Image) -> np.ndarray:
    hsv = np.array(img.convert("HSV")).astype(np.float32)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    hue_deg = h * 360.0 / 255.0
    return (hue_deg >= 15) & (hue_deg <= 65) & (s > 40) & (v > 60) & (v < 250)


def add_shine(img: Image.Image) -> Image.Image:
    """Restore genuine highlight/shadow contrast to FLUX's gold rendering.

    Confirmed on real regenerations (2026-08-14, ER22_13 and ER22_105, both
    using the current prompt's explicit three-tone-palette-with-specular-
    glint instructions): FLUX still delivers a single near-flat amber tone
    across the whole piece -- no highlight band, no shadow depth, no crisp
    glint on convex points. It reads as a flat illustration, not photographed
    metal. This is the same class of failure standardize_gold already exists
    for (FLUX won't reliably hit a described target through prompting alone)
    -- so fix it the same deterministic way, not with more prompt wording.

    Relights using a proper (if crude) surface-normal model instead of a
    2D filter, because two earlier, purely-2D attempts both failed in
    opposite ways:
    - CLAHE + unsharp mask + a flat diagonal gradient (first attempt): fixed
      pieces with SOME existing texture, but on ER22_105's large smooth
      trapezoid panel there was nothing for CLAHE to amplify, so it barely
      moved even at double strength -- confirmed by testing 2x the clip
      limit and seeing almost no change.
    - Full bevel/normal-map relighting using BOTH a per-blob silhouette
      distance-transform AND a fine Canny-edge distance-transform for
      height, with high normal strength (12) and a sharp specular exponent
      (40) (second attempt): fixed the flat-panel case beautifully, but on
      ER22_109's beaded border it turned smooth round beads into lumpy,
      "hammered" blobs and covered every surface in chaotic speckle --
      confirmed on a 2x crop, invisible at thumbnail scale, which is exactly
      why it shipped broken the first time and had to be caught by re-review.

    The fix that survived full-resolution crop inspection on both cases
    drops the fine-edge height component entirely (that was the main source
    of the hammered look) and turns everything down hard: normal strength
    12 -> 3, specular exponent 40 -> 18, specular intensity 0.9 -> 0.45,
    diffuse intensity 0.35 -> 0.22, plus a heavier final blur on the height
    map before computing normals so only large-scale shape drives lighting,
    never small-scale bumps.

    Height map: Euclidean distance transform of the gold mask, heavily
    Gaussian-blurred. Within any one connected blob this naturally peaks at
    that blob's own medial axis/centre -- exactly the "each facet domes
    toward its own middle" effect a bevel/emboss layer style produces, with
    no per-facet segmentation needed. Normals come from the height map's
    Sobel gradients; a single simulated light (upper-left, matching the
    old gradient's direction for consistency) drives a Lambertian diffuse
    term plus a Blinn-Phong specular term for the crisp glint.

    Deliberately run BEFORE standardize_gold: that function corrects the
    MEAN tone within the gold mask while preserving each pixel's relative
    brightness ratio to its neighbours (see its own docstring) -- so
    whatever contrast this function adds survives the colour correction
    that comes after it, instead of being averaged away.
    """
    arr = np.array(img.convert("RGB"))
    mask = gold_mask(img)
    if not mask.any():
        return img
    height, width = mask.shape
    mask_u8 = mask.astype(np.uint8) * 255

    height_map = cv2.distanceTransform(mask_u8, cv2.DIST_L2, 5).astype(np.float32)
    height_map = cv2.GaussianBlur(height_map, (0, 0), sigmaX=11)
    peak = height_map.max()
    if peak > 0:
        height_map /= peak
    # Second, heavier blur: normals are computed from THIS map, so any
    # small-scale variation that survives to here becomes lighting -- the
    # hammered-bead failure came from exactly this kind of leftover detail.
    height_map = cv2.GaussianBlur(height_map, (0, 0), sigmaX=6)

    grad_x = cv2.Sobel(height_map, cv2.CV_32F, 1, 0, ksize=5)
    grad_y = cv2.Sobel(height_map, cv2.CV_32F, 0, 1, ksize=5)
    normal_strength = 3.0
    unit_z = np.ones_like(height_map)
    magnitude = np.sqrt(
        (grad_x * normal_strength) ** 2 + (grad_y * normal_strength) ** 2 + unit_z**2
    )
    normal_x = -grad_x * normal_strength / magnitude
    normal_y = -grad_y * normal_strength / magnitude
    normal_z = unit_z / magnitude

    light = np.array((-0.5, -0.5, 0.75), dtype=np.float32)
    light /= np.linalg.norm(light)
    view = np.array((0.0, 0.0, 1.0), dtype=np.float32)
    half_vector = light + view
    half_vector /= np.linalg.norm(half_vector)

    diffuse = np.clip(normal_x * light[0] + normal_y * light[1] + normal_z * light[2], 0, 1)
    specular_dot = np.clip(
        normal_x * half_vector[0] + normal_y * half_vector[1] + normal_z * half_vector[2], 0, 1
    )
    specular = specular_dot**18

    sharpened = arr.astype(np.float32).copy()
    diffuse_strength, specular_strength = 0.22, 0.45
    for channel in range(3):
        plane = sharpened[..., channel]
        lit = plane * (1 + diffuse_strength * (diffuse - 0.5) * 2)
        lit = lit + specular * 255 * specular_strength
        plane[mask] = lit[mask]
        sharpened[..., channel] = plane

    # Fine monochromatic grain, slightly streaked horizontally to read as
    # micro-scratches rather than uniform digital noise. A perfectly smooth
    # surface -- which is what the first three passes alone produce even
    # after adding contrast -- still reads as rendered, not photographed;
    # real macro jewellery photography always shows this at close range.
    # Standard technique in commercial jewellery retouching for exactly this
    # "AI metal looks flat/plastic" problem (see e.g. frequency-separation
    # and synthetic-grain workflows documented at cloudretouch.com and
    # imageworkindia.com) -- confirmed visible on a 3x crop without being
    # visible as noise at normal viewing size.
    noise = np.random.default_rng().normal(0, 6.0, (height, width)).astype(np.float32)
    streak_kernel = np.ones((1, 5), np.float32) / 5
    noise = cv2.filter2D(noise, -1, streak_kernel)
    for channel in range(3):
        plane = sharpened[..., channel]
        plane[mask] += noise[mask]
        sharpened[..., channel] = plane

    out = arr.copy()
    out[mask] = np.clip(sharpened[mask], 0, 255)
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"), mode="RGB")


def standardize_gold(img: Image.Image) -> Image.Image:
    arr = np.array(img).astype(np.float32)
    mask = gold_mask(img)
    if not mask.any():
        return img

    target = np.array(TARGET_RGB, dtype=np.float32)
    current_mean = arr[..., :3][mask].mean(axis=0)
    gain = np.clip(target / np.clip(current_mean, 1.0, None), MIN_GAIN, MAX_GAIN)

    out = arr[..., :3].copy()
    for c in range(3):
        channel = out[..., c]
        channel[mask] = channel[mask] * gain[c]
        out[..., c] = channel

    out = np.clip(out, 0, 255).astype("uint8")
    return Image.fromarray(out, mode="RGB")
