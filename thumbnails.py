"""Serve small, cached previews instead of full-resolution catalogue images.

The web UI rendered every queue and result tile straight from the original
file. Measured 2026-09-01: input/ alone was 328 MB across 38 files, one of
them 38.5 MB, and a stitched composite at 8628x8051 decodes to roughly 278 MB
of bitmap in the browser. A page showing a dozen tiles therefore asked the
browser for gigabytes of decoded image, which is what made the UI sluggish
and left controls unresponsive -- the main thread was busy decoding, not
broken.

Previews are cached on disk, keyed by source path, mtime and width, so a
given tile is resized once and then served as a small static file.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / "data" / "_thumb_cache"
MAX_WIDTH = 2000
MIN_WIDTH = 32


def scaled(source: Path, width: int) -> Path:
    """Return a cached preview of `source` at `width` px.

    Fail-open: any problem returns `source` unchanged, so a preview issue can
    never stop an image being served.
    """
    try:
        width = max(MIN_WIDTH, min(int(width), MAX_WIDTH))
        source = Path(source)
        stat = source.stat()
        if stat.st_size < 200_000:
            return source          # already small; resizing would cost more than it saves
        key = hashlib.sha256(
            f"{source.resolve()}|{stat.st_mtime_ns}|{width}".encode("utf-8")
        ).hexdigest()[:24]
        cached = CACHE_DIR / f"{key}.jpg"
        if cached.is_file():
            return cached

        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None      # composites legitimately exceed the bomb guard
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image = image.convert("RGB")
            if image.width > width:
                height = max(1, round(image.height * width / image.width))
                image = image.resize((width, height), Image.Resampling.LANCZOS)
            temporary = cached.with_suffix(".tmp.jpg")
            image.save(temporary, format="JPEG", quality=82, optimize=True)
        temporary.replace(cached)
        return cached
    except Exception:
        log.exception("thumbnail failed for %s; serving the original", source)
        return Path(source)
