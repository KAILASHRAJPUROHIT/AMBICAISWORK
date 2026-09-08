"""Reduce a stitched three-panel reference sheet to its MAIN panel.

FLUX.2 renders a composite reference badly: handed a sheet with a main panel
and two angle panels, it has to decide which panel is authoritative and ends
up blending them.  Measured 2026-08-31 across eight rings, feeding the main
panel alone fixed every fidelity failure we had -- LR22_132 stopped rendering
as an unrelated vertical ornament, LR22_407 kept its chevron instead of
flattening to a plain band, LR22_91 and LR22_95 regained dropped elements.
BFL document single-reference editing as the supported path for edits; the
three-panel sheet was never that.

The sheet is still produced and still shown for human review.  Only the image
handed to the renderer changes.  Fail-open throughout: any problem here
returns the original path, so a capture is never blocked.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

SUFFIX = "_mainref.jpg"


def main_panel(source: str | Path) -> Path:
    """Return a single-reference image for `source`.

    Prefers a `<stem>_main.jpg` written at capture time (the full-resolution
    main crop, before it was scaled into the sheet).  Otherwise extracts the
    main panel from the sheet and caches it next to the source.  Returns the
    original path unchanged if anything at all goes wrong.
    """
    source = Path(source)
    try:
        captured = source.with_name(f"{source.stem}_main.jpg")
        if captured.is_file():
            return captured

        # Cache OUTSIDE the source folder. input/ and capture_intake/ are
        # scanned as work queues, so a sibling <stem>_mainref.jpg was listed
        # as an item in its own right (2026-09-01). Key on the source path so
        # two categories sharing a stem cannot collide.
        import hashlib
        digest = hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()[:16]
        cache_dir = Path(__file__).resolve().parent / "data" / "_single_reference_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / f"{source.stem}_{digest}{SUFFIX}"
        if cached.is_file():
            return cached

        import cv2
        import numpy as np

        image = cv2.imread(str(source))
        if image is None:
            return source
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Panels are photographs on a dark ground; the sheet's own margins and
        # label bands are near-white.  The main panel is the largest non-white
        # region whose centre sits in the upper part of the sheet.
        count, _labels, stats, _ = cv2.connectedComponentsWithStats(
            (grey < 200).astype(np.uint8), 8
        )
        best = None
        for index in range(1, count):
            x, y, w, h, area = stats[index]
            if y + h / 2 < image.shape[0] * 0.60 and (best is None or area > best[4]):
                best = (x, y, w, h, area)
        if best is None:
            return source
        x, y, w, h, _ = best
        # A sheet whose "main panel" is nearly the whole image is not a sheet:
        # it is already a single photograph, so leave it alone.
        if w * h > grey.size * 0.85:
            return source
        cv2.imwrite(str(cached), image[y:y + h, x:x + w], [cv2.IMWRITE_JPEG_QUALITY, 100])
        log.info("single_reference: %s -> %s (%dx%d)", source.name, cached.name, w, h)
        return cached
    except Exception:
        log.exception("single_reference failed for %s; using the source unchanged", source)
        return source


def label_from(path: str | Path) -> str:
    """Original item label for a path this module may have rewritten.

    main_panel() caches as "<stem>_<16 hex>_mainref.jpg". The guard keys
    per-item geometry hints on the source filename, so without stripping
    that suffix BL18_10 and BL22_43 silently lost their measured contracts
    (2026-09-01).
    """
    import re
    stem = Path(path).stem
    return re.sub(r"_[0-9a-f]{16}" + re.escape(SUFFIX).replace("\.jpg", "") + r"$", "", stem)
