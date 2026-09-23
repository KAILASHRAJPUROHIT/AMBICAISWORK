"""Remove text and stray marks from a delivered catalogue image.

FLUX.2 intermittently paints text into the product shot -- garbled panel
captions ("MAIN SHNIN", "RIGHT ANGLE"), invented brand marks ("MIORFEUN"),
and stray strings like "22 EAN" or a fake copyright. Prompt wording reduced
this from roughly 60% of renders to about 1 in 7 (2026-09-01) but cannot
reach zero: the model decides, and it is not deterministic.

This is the deterministic backstop. The delivered image is specified as
nothing but the ornament on a plain white ground, so any DARK mark that is
not part of the ornament's own connected form, and is small relative to it,
cannot be product. Those are erased to the background.

Deliberately conservative:
  * only dark marks qualify -- a soft contact shadow is light and is kept
  * only components far smaller than the piece qualify, so the second half
    of a matched pair, or a detached dangle, is never removed
  * a component touching the piece is never removed
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

DARK_MAX = 150          # a mark must be at least this dark to be considered
BACKGROUND_MIN = 238    # at/above this is background
MAX_AREA_FRACTION = 0.02  # ...and under 2% of the ornament's own area
SEPARATION_PX = 6       # ...and not touching the ornament


def _ornament_mask(grey: np.ndarray) -> np.ndarray | None:
    subject = (grey < BACKGROUND_MIN).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(subject, 8)
    if count <= 1:
        return None
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (labels == largest)


def strip(img: Image.Image) -> tuple[Image.Image, int]:
    """Returns (cleaned image, number of marks removed)."""
    arr = np.array(img.convert("RGB"))
    grey = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    ornament = _ornament_mask(grey)
    if ornament is None:
        return img, 0
    ornament_area = int(ornament.sum())
    # Anything the ornament could plausibly touch stays untouchable.
    near = cv2.dilate(ornament.astype(np.uint8),
                      np.ones((SEPARATION_PX * 2 + 1,) * 2, np.uint8)) > 0

    dark = ((grey < DARK_MAX) & ~near).astype(np.uint8)
    if not dark.any():
        return img, 0

    count, labels, stats, _ = cv2.connectedComponentsWithStats(dark, 8)
    removal = np.zeros(grey.shape, np.uint8)
    removed = 0
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] <= ornament_area * MAX_AREA_FRACTION:
            removal[labels == index] = 255
            removed += 1
    if not removed:
        return img, 0

    # The dark core of a glyph is only part of it -- anti-aliased edges sit
    # well above DARK_MAX and were leaving a legible ghost. Clear each mark's
    # whole neighbourhood instead: inside a box around a confirmed mark, and
    # still clear of the ornament, anything that is not background IS the
    # mark. The ornament is protected throughout by `near`.
    boxes = cv2.dilate(removal, np.ones((15, 15), np.uint8)) > 0
    removal = (boxes & (grey < BACKGROUND_MIN) & ~near)

    # Paint out to the local background rather than inpainting: the ground is
    # a flat white field, so the honest fill is the field itself.
    background = int(np.median(grey[grey >= BACKGROUND_MIN])) if (grey >= BACKGROUND_MIN).any() else 255
    arr[removal] = background
    return Image.fromarray(arr), removed
