"""
hole_detection.py — deterministic, local classifier for "is this dark region
inside a jewellery photo a hollow lattice gap, or real black enamel?"

Real problem this targets: jewellery is shot on black velvet, so both a
hollow openwork gap (velvet showing through the metal lattice) and genuine
black enamel look the same colour to a vision model — and generative engines
have repeatedly guessed wrong, filling real holes in with solid black
(TP22_138, 2026-08-02). Asking harder in a prompt hasn't fixed this across
three separate attempts this session. This replaces the guess with a
measurement: a hollow gap is physically the SAME material as the background
velvet (same colour, same texture) just spatially walled off by metal bars;
real enamel is a manufactured surface with different reflectance. That
difference is measurable with classical CV — no AI model, no API call.

Algorithm:
  1. Threshold near-black pixels using the image's OWN background colour as
     the reference (not a fixed constant — velvet tone varies photo to
     photo).
  2. Flood-fill from the image border through connected dark pixels — that
     reachable region is definitely background velvet (it's physically
     continuous with the outside-the-jewellery area).
  3. Every OTHER dark connected component is enclosed/isolated — walled off
     by non-dark (metal) pixels on every side. These are the candidates.
  4. For each candidate, compare its mean colour + local texture against the
     confirmed background sample. Close match -> hollow gap (transparent
     through-hole). Meaningful deviation -> real enamel (preserve as colour).
"""

import numpy as np
from PIL import Image
from scipy import ndimage


def _dark_threshold(bg_sample_luma: float) -> float:
    # Velvet backgrounds run dark but not identical photo to photo (lighting,
    # compression). Threshold relative to the measured background brightness
    # rather than a fixed constant, with headroom for JPEG noise.
    return min(60.0, bg_sample_luma + 25.0)


def _sample_background(gray: np.ndarray, margin_frac: float = 0.04) -> float:
    """Mean luma of the image's outer margin — definitely background, never
    touches the jewellery in any of our studio shots (jewellery is always
    composed with clean space around it per the studio framing rules)."""
    h, w = gray.shape
    mh, mw = int(h * margin_frac), int(w * margin_frac)
    strips = [gray[:mh, :], gray[-mh:, :], gray[:, :mw], gray[:, -mw:]]
    return float(np.mean([s.mean() for s in strips]))


def classify_dark_regions(image_path: str, min_region_px: int = 30) -> dict:
    """Return {"ok": True, "background_lab": (L,a,b), "regions": [...]}
    where each region is {"bbox": (x0,y0,x1,y1), "px_count": int,
    "classification": "hole"|"enamel", "color_distance": float}.

    Regions are enclosed dark connected components not reachable from the
    image border. "hole" means it statistically matches the confirmed
    background sample; "enamel" means it measurably doesn't.
    """
    with Image.open(image_path) as raw:
        im = raw.convert("RGB")
    # Full raw captures run 6192x4128 (25MP) — connected-component labeling
    # at that resolution takes ~2 minutes, which is a non-starter when this
    # runs per prompt-build call (twice per pair: once for each engine's
    # prompt). Region classification doesn't need full resolution; a scaled
    # copy still resolves lattice gaps and enamel panels fine, at a fraction
    # of the cost. Bboxes are scaled back up to original-image coordinates
    # before returning, so callers never see the working resolution.
    scale = 1.0
    max_side = 1600
    if max(im.size) > max_side:
        scale = max_side / max(im.size)
        im_small = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    else:
        im_small = im
    arr = np.array(im_small).astype(np.float32)
    gray = arr.mean(axis=2)
    h, w = gray.shape

    bg_luma = _sample_background(gray)
    threshold = _dark_threshold(bg_luma)
    dark = gray < threshold

    # Flood-fill connectivity from the border through dark pixels only.
    labeled, n = ndimage.label(dark, structure=np.ones((3, 3)))
    border_labels = set(labeled[0, :]) | set(labeled[-1, :]) | \
                    set(labeled[:, 0]) | set(labeled[:, -1])
    border_labels.discard(0)

    # Background reference stats: sample the actual confirmed-background
    # connected region's pixels (not just the margin strip) for a more
    # representative colour+texture signature.
    if border_labels:
        bg_mask = np.isin(labeled, list(border_labels))
    else:
        bg_mask = np.zeros_like(dark)
    if bg_mask.sum() < 100:
        # Fallback: use the margin strips directly if flood-fill found
        # nothing (e.g. a full-bleed dark image with no light border).
        mh, mw = int(h * 0.04), int(w * 0.04)
        bg_mask = np.zeros_like(dark)
        bg_mask[:mh, :] = True
        bg_mask[-mh:, :] = True
        bg_mask[:, :mw] = True
        bg_mask[:, -mw:] = True

    bg_rgb_mean = arr[bg_mask].mean(axis=0)
    bg_texture = float(np.std(gray[bg_mask]))

    regions = []
    for label_id in range(1, n + 1):
        if label_id in border_labels:
            continue
        region_mask = labeled == label_id
        px_count = int(region_mask.sum())
        if px_count < min_region_px:
            continue

        ys, xs = np.where(region_mask)
        bbox = (int(xs.min() / scale), int(ys.min() / scale),
                int((xs.max() + 1) / scale), int((ys.max() + 1) / scale))

        region_rgb_mean = arr[region_mask].mean(axis=0)
        region_texture = float(np.std(gray[region_mask]))

        color_distance = float(np.linalg.norm(region_rgb_mean - bg_rgb_mean))
        texture_ratio = region_texture / bg_texture if bg_texture > 1e-3 else 1.0

        # A hollow gap is the same material as the background: close colour
        # AND comparable texture variance. A meaningfully different colour
        # (enamel pigment) or a much flatter/glossier texture (painted
        # surface vs velvet nap) breaks the match.
        is_hole = color_distance < 18.0 and 0.4 < texture_ratio < 2.5

        regions.append({
            "bbox": bbox,
            "px_count": px_count,
            "classification": "hole" if is_hole else "enamel",
            "color_distance": round(color_distance, 2),
            "texture_ratio": round(texture_ratio, 2),
        })

    return {
        "ok": True,
        "background_rgb": tuple(round(float(v), 1) for v in bg_rgb_mean),
        "background_texture": round(bg_texture, 2),
        "threshold_used": round(threshold, 1),
        "regions": regions,
    }
