"""Put every delivered piece at the same size in the frame.

Centring was already as consistent as the reference catalogue we benchmark
against (centre-X sd 1.1 vs their 1.3), but SCALE was not: measured across 61
deliveries the piece occupied anywhere from 17.9% to 90.4% of the frame width
(sd 16.9) against their sd 7.1. Side by side that reads as chaos even when
colour, pose and background all match.

Prompt wording cannot fix it -- asking for "about half the frame height"
produced renders averaging 80%. This does it deterministically instead: the
piece is measured, scaled so its longest side occupies a fixed fraction of the
canvas, and centred on the background. Every category gets the same treatment.

Runs AFTER stray-mark removal, so leftover text can never inflate the
measured bounding box.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

TARGET_LONGEST_SIDE = 0.80   # piece's longest dimension, as a fraction of the canvas
CONTENT_MAX_LUMA = 230       # below this is the piece; above is background/soft shadow
MIN_CONTENT_PIXELS = 2000


def fit(img: Image.Image, target: float = TARGET_LONGEST_SIDE) -> tuple[Image.Image, float]:
    """Scale and centre `img`'s content. Returns (image, applied scale).

    Fail-open: any problem returns the image untouched with scale 1.0, so a
    delivery is never blocked by this step.
    """
    try:
        rgb = img.convert("RGB")
        arr = np.array(rgb)
        height, width = arr.shape[:2]
        grey = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        content = grey < CONTENT_MAX_LUMA
        if int(content.sum()) < MIN_CONTENT_PIXELS:
            return img, 1.0

        rows = np.where(content.any(axis=1))[0]
        cols = np.where(content.any(axis=0))[0]
        y0, y1 = int(rows[0]), int(rows[-1]) + 1
        x0, x1 = int(cols[0]), int(cols[-1]) + 1
        box_w, box_h = x1 - x0, y1 - y0
        if box_w <= 0 or box_h <= 0:
            return img, 1.0

        edge = min(width, height)
        scale = (target * edge) / max(box_w, box_h)
        new_w = max(1, int(round(box_w * scale)))
        new_h = max(1, int(round(box_h * scale)))
        if new_w > width or new_h > height:
            return img, 1.0

        # Background is sampled from the real corners rather than assumed
        # pure white -- deliveries sit on a near-white field, not #FFFFFF.
        corners = np.concatenate([arr[:8, :8].reshape(-1, 3), arr[:8, -8:].reshape(-1, 3),
                                  arr[-8:, :8].reshape(-1, 3), arr[-8:, -8:].reshape(-1, 3)])
        background = tuple(int(v) for v in np.median(corners, axis=0))

        piece = rgb.crop((x0, y0, x1, y1)).resize((new_w, new_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (width, height), background)
        canvas.paste(piece, ((width - new_w) // 2, (height - new_h) // 2))
        return canvas, scale
    except Exception:
        return img, 1.0
