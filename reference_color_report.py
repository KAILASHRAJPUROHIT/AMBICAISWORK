"""Deterministic (non-AI) colour-presence report for a raw capture photo.

WHY NOT A VISION MODEL: local_ai_cannot_verify_jewellery_design (see memory) --
qwen2.5vl and CLIP were both measured to fail at full design-match verification
on this exact dataset. But this isn't that problem. "Does any non-gold
saturated colour exist in this photo, and roughly where" is a narrow,
measurable pixel question, not a design-understanding one -- the same class
of problem the proven "pixel veto on materials" technique (memory) already
solved 10/10 on known truth. This module is that technique, rebuilt fresh
since the original implementation didn't survive the local-AI pipeline strip
(task #57).

Safeguards against false positives on a real capture photo (unlike a
clean AI output, these have a black velvet stand, a white paper price tag,
hands, shop reflections, and sometimes a QR code sticker in frame):
  - Product-region gate: colour is measured only inside focus-localised
    jewellery boxes. This prevents a sharp blue counter reflection, clothing,
    skin, or background signage from becoming a product-colour instruction.
  - Gold-proximity gate: coloured pixels must touch or sit inside the gold
    structure. A coloured object merely sharing the jewellery's box is not
    treated as a stone or enamel.
  - Sharpness gate: only in-focus pixels count. The velvet stand and tag are
    typically slightly out of the macro focal plane; Laplacian-percentile
    filtering (same technique as the proven gold-and-sharp localiser) drops
    them before colour is ever measured.
  - Saturation/value floor: near-black (velvet), near-white (tag paper,
    background), and low-saturation (grey QR modules) pixels are excluded
    from the "coloured" bucket regardless of sharpness.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

GOLD_HUE_RANGE = (15, 65)  # degrees, matches color_standardize.gold_mask
MIN_SATURATION = 60  # 0-255
MIN_VALUE = 60
MAX_VALUE = 245  # excludes blown-out white/highlight pixels
SHARPNESS_PERCENTILE = 80  # only the sharpest 20% of pixels are trusted
MIN_COLOURED_PIXEL_FRACTION = 0.0015  # noise floor, ~0.15% of sharp pixels
MAX_LOCALISATION_BOXES = 4

_HUE_NAMES = (
    (15, "orange/gold"), (45, "yellow"), (75, "yellow-green"), (150, "green"),
    (200, "cyan"), (250, "blue"), (290, "purple"), (330, "pink/magenta"),
    (350, "red"), (360, "red"),
)


def _hue_name(hue_deg: float) -> str:
    for boundary, name in _HUE_NAMES:
        if hue_deg <= boundary:
            return name
    return "red"


def _sharpness_map(gray: np.ndarray) -> np.ndarray:
    import cv2
    return np.abs(cv2.Laplacian(gray, cv2.CV_64F, ksize=3))


def _position_label(mask: np.ndarray, bounds: tuple[int, int, int, int] | None = None) -> str:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return "unknown position"
    if bounds is None:
        x0, y0, x1, y1 = 0, 0, mask.shape[1], mask.shape[0]
    else:
        x0, y0, x1, y1 = bounds
    width, height = max(1, x1 - x0), max(1, y1 - y0)
    cx, cy = (xs.mean() - x0) / width, (ys.mean() - y0) / height
    vertical = "top" if cy < 0.4 else ("bottom" if cy > 0.6 else "middle")
    horizontal = "left" if cx < 0.4 else ("right" if cx > 0.6 else "centre")
    if vertical == "middle" and horizontal == "centre":
        return "centre"
    return f"{vertical}-{horizontal}"


def _product_region_mask(arr: np.ndarray) -> tuple[np.ndarray | None, list[list[int]]]:
    """Return conservative focus-localised jewellery regions.

    This deliberately uses ``focus_boxes`` rather than SAM2: it is local,
    deterministic, free, and already proven on these capture plates. Failure
    returns no mask, which causes a neutral preservation instruction rather
    than inventing a measured colour.
    """
    import cv2

    try:
        from sam_locate import focus_boxes

        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        boxes = focus_boxes(bgr, expect=MAX_LOCALISATION_BOXES)
    except Exception:
        boxes = []
    if not boxes:
        return None, []

    height, width = arr.shape[:2]
    region = np.zeros((height, width), dtype=bool)
    clean_boxes: list[list[int]] = []
    for raw_box in boxes:
        x0, y0, x1, y1 = (int(v) for v in raw_box)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(width, x1), min(height, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        region[y0:y1, x0:x1] = True
        clean_boxes.append([x0, y0, x1, y1])
    return (region, clean_boxes) if clean_boxes else (None, [])


def _near_gold_mask(hue_deg: np.ndarray, sat: np.ndarray, val: np.ndarray,
                    boxes: list[list[int]]) -> np.ndarray:
    """Limit candidates to pixels embedded in or immediately beside gold."""
    import cv2

    gold = ((hue_deg >= GOLD_HUE_RANGE[0]) & (hue_deg <= GOLD_HUE_RANGE[1])
            & (sat > 40) & (val > MIN_VALUE) & (val < 250))
    near_gold = np.zeros(gold.shape, dtype=bool)
    for x0, y0, x1, y1 in boxes:
        roi = gold[y0:y1, x0:x1].astype(np.uint8)
        radius = max(5, min(41, int(round(0.04 * max(x1 - x0, y1 - y0)))))
        kernel_size = radius * 2 + 1
        expanded = cv2.dilate(
            roi, np.ones((kernel_size, kernel_size), np.uint8), iterations=1
        )
        near_gold[y0:y1, x0:x1] |= expanded.astype(bool)
    return near_gold


def _bounds_for_mask(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def analyze(image_path: str) -> dict:
    """Measure whether the reference photo shows any non-gold coloured
    stone/stud/enamel, and if so, its approximate hue and position.

    Returns a report dict; report["prompt_line"] is the single sentence
    meant to be appended to the generation prompt for this specific item.
    """
    import cv2

    with Image.open(image_path) as opened:
        img = opened.convert("RGB")
    arr = np.array(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)
    hue_deg = hsv[..., 0] * 2.0  # OpenCV HSV hue is 0-179
    sat, val = hsv[..., 1], hsv[..., 2]

    product_region, boxes = _product_region_mask(arr)
    if product_region is None:
        return {
            "has_colour": None,
            "colour_measurement": "inconclusive_no_product_region",
            "localisation_boxes": [],
            "prompt_line": "Use exactly the jewellery material palette visible in Image 1. Preserve each visible stone and enamel colour at its matching product location, and render all other product surfaces in gold.",
        }

    sharpness = _sharpness_map(gray)
    sharp_floor = np.percentile(sharpness, SHARPNESS_PERCENTILE)
    sharp_mask = sharpness >= sharp_floor

    saturated_mask = (sat > MIN_SATURATION) & (val > MIN_VALUE) & (val < MAX_VALUE)
    near_gold = _near_gold_mask(hue_deg, sat, val, boxes)
    trusted_product = sharp_mask & product_region & near_gold
    in_focus_saturated = trusted_product & saturated_mask
    gold_hue = (hue_deg >= GOLD_HUE_RANGE[0]) & (hue_deg <= GOLD_HUE_RANGE[1])
    coloured_mask = in_focus_saturated & ~gold_hue

    total_sharp = int(trusted_product.sum())
    coloured_count = int(coloured_mask.sum())
    fraction = coloured_count / total_sharp if total_sharp else 0.0

    if fraction < MIN_COLOURED_PIXEL_FRACTION:
        return {
            "has_colour": False,
            "colour_measurement": "product_region",
            "localisation_boxes": boxes,
            "coloured_pixel_fraction": round(fraction, 5),
            "prompt_line": "Reference-measured product evidence: use gold for this piece's metal and decorative surfaces. Preserve every clear or white stone exactly as Image 1 shows it.",
        }

    hue_values = hue_deg[coloured_mask]
    dominant_hue = float(np.median(hue_values))
    hue_label = _hue_name(dominant_hue)
    position = _position_label(coloured_mask, _bounds_for_mask(product_region))
    return {
        "has_colour": True,
        "colour_measurement": "product_region",
        "localisation_boxes": boxes,
        "coloured_pixel_fraction": round(fraction, 5),
        "dominant_hue_degrees": round(dominant_hue, 1),
        "hue_label": hue_label,
        "position": position,
        # Do not turn a coarse single-hue statistic into a generation order.
        # Multi-colour pieces can have green and magenta enamel whose median
        # hue is cyan, even though no cyan exists. The image is authoritative.
        "prompt_line": "Reference-measured product evidence: Image 1 contains genuine coloured stone or enamel surfaces embedded within the jewellery. Copy each visible product colour exactly at its corresponding jewellery location and render every remaining non-stone product surface in gold.",
    }
