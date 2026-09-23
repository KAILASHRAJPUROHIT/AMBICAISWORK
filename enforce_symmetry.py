"""Force literal left/right mirror-symmetry on a matched-pair catalogue shot.

WHY: prompt wording ("keep both sides... true mirror images of each other")
measurably reduced but did not eliminate shape drift between the two
earrings of a pair -- confirmed on ER22_13, where the left top loop rendered
round and the right rendered as a pointed teardrop even after adding an
explicit symmetry clause. A generative model renders each side through a
partially independent stochastic path; no amount of prompt wording can
GUARANTEE pixel-identical geometry, because the model isn't literally
copying one side onto the other, it's generating two similar-but-separate
regions. Only an explicit copy-and-mirror step can guarantee that.

Approach: locate the two ornament blobs (connected components of non-white
pixels), treat the larger/more-complete one as the source of truth, and
replace the other with a horizontally-flipped copy of it, aligned by
bounding-box centre. This makes the two sides literally identical by
construction -- not "more likely to match," but mirror-copies of the same
pixels.

Deliberately conservative about when to act: only touches images with
exactly two well-separated blobs of comparable size (a genuine earring/
jhumka pair shot). Anything else (single pendant, ring, three-piece set,
oddly cropped result) is left untouched rather than guessed at.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

MIN_BLOB_AREA_FRACTION = 0.01  # ignore tiny specks/noise
SIZE_RATIO_TOLERANCE = 3.0  # blobs more different in area than this aren't a clean pair


def _foreground_mask(arr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return gray < 245  # not near-pure-white background


def _largest_two_components(mask: np.ndarray) -> list[dict] | None:
    mask_u8 = mask.astype(np.uint8) * 255
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
    total_pixels = mask.shape[0] * mask.shape[1]
    blobs = []
    for label in range(1, count):
        area = stats[label, cv2.CC_STAT_AREA]
        if area / total_pixels < MIN_BLOB_AREA_FRACTION:
            continue
        x, y, w, h = (
            stats[label, cv2.CC_STAT_LEFT], stats[label, cv2.CC_STAT_TOP],
            stats[label, cv2.CC_STAT_WIDTH], stats[label, cv2.CC_STAT_HEIGHT],
        )
        blobs.append({"label": label, "area": area, "bbox": (x, y, w, h), "cx": centroids[label][0]})
    if len(blobs) != 2:
        return None
    blobs.sort(key=lambda b: b["cx"])
    return blobs


def enforce_pair_symmetry(img: Image.Image) -> Image.Image:
    arr = np.array(img.convert("RGB"))
    mask = _foreground_mask(arr)
    blobs = _largest_two_components(mask)
    if blobs is None:
        return img  # not a clean two-ornament pair shot -- leave untouched

    left, right = blobs
    larger, smaller = (left, right) if left["area"] >= right["area"] else (right, left)
    if larger["area"] / max(smaller["area"], 1) > SIZE_RATIO_TOLERANCE:
        return img  # too different in size to be a genuine matched pair -- leave untouched

    lx, ly, lw, lh = larger["bbox"]
    sx, sy, sw, sh = smaller["bbox"]
    source_patch = arr[ly : ly + lh, lx : lx + lw]
    mirrored = cv2.flip(source_patch, 1)  # horizontal flip

    out = arr.copy()
    canvas_height, canvas_width = out.shape[:2]

    # Centre the mirrored patch on the smaller blob's own bounding-box centre,
    # so it lands in the correct position even if the original two blobs
    # weren't perfectly aligned in scale or vertical position.
    target_cx, target_cy = sx + sw / 2.0, sy + sh / 2.0
    paste_x = int(round(target_cx - lw / 2.0))
    paste_y = int(round(target_cy - lh / 2.0))

    # Clip the paste region to the canvas bounds, cropping the mirrored
    # patch to match if it would otherwise run off the edge.
    src_x0, src_y0 = 0, 0
    dst_x0, dst_y0 = paste_x, paste_y
    if dst_x0 < 0:
        src_x0 = -dst_x0
        dst_x0 = 0
    if dst_y0 < 0:
        src_y0 = -dst_y0
        dst_y0 = 0
    dst_x1 = min(canvas_width, paste_x + lw)
    dst_y1 = min(canvas_height, paste_y + lh)
    src_x1 = src_x0 + (dst_x1 - dst_x0)
    src_y1 = src_y0 + (dst_y1 - dst_y0)
    if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return img  # degenerate geometry -- leave untouched rather than risk corruption

    # Erase the smaller blob's own footprint first, so no fragment of the
    # original asymmetric side survives underneath the mirrored replacement.
    # Fill with the LOCAL background colour, not hardcoded pure white --
    # confirmed on ER22_13 that these renders carry a faint background
    # gradient/texture, so a flat-255 fill left a visible seam at the erased
    # region's edge. Sampling a thin margin around the bbox picks up
    # whatever that local tone actually is.
    margin = 12
    top = out[max(0, sy - margin) : sy, sx : sx + sw]
    bottom = out[sy + sh : sy + sh + margin, sx : sx + sw]
    border_pixels = np.concatenate(
        [p.reshape(-1, 3) for p in (top, bottom) if p.size], axis=0
    )
    fill_colour = (
        np.median(border_pixels, axis=0) if border_pixels.size else np.array([255, 255, 255])
    )
    out[sy : sy + sh, sx : sx + sw] = fill_colour
    out[dst_y0:dst_y1, dst_x0:dst_x1] = mirrored[src_y0:src_y1, src_x0:src_x1]

    return Image.fromarray(out, mode="RGB")
