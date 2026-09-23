"""
photogrammetry.py — estimate a jewellery piece's real-world size (mm) from
camera EXIF metadata, when the capture device recorded enough of it.

Real motivation: some captures are shot close-up, some from farther back
with more zoom — the RAW PIXEL size of the jewellery in the photo says
nothing about its true physical size without knowing how the photo was
taken. Weight alone doesn't solve this either — a hollow/openwork design
weighs less than a solid one of the same visual size, so a light piece can
still be physically large (confirmed on TP22_138 itself: an openwork frame
design). The one thing that DOES give true physical size is basic
photogrammetry: focal length + focus distance + sensor size + image pixel
width together fix the real-world width visible in the frame, independent
of weight or hollow/solid construction.

Confirmed by direct testing (2026-08-02) against real capture files:
- Sony ZV-E10M2 captures (this business's main camera) DO record focal
  length AND focus distance, but only in a proprietary MakerNote block that
  plain EXIF readers (PIL, exifread) can't decode — needs ExifTool, which is
  vendored in tools/exiftool-13.59_64/.
- A second device used for some batches (identifies itself as model
  "A069P", likely a phone) records ONLY focal length, no focus/subject
  distance at all, and its hyperfocal-distance value is a fixed lens
  property, not a measured distance — not usable.

This means metadata-based sizing is a BEST-EFFORT PRIMARY signal, not a
guaranteed one. estimate_mm_per_pixel() returns None with an explicit reason
whenever any required field is missing or the camera's sensor size isn't in
SENSOR_WIDTHS_MM — callers must have a fallback (tag-based visual
calibration, or a wide-tolerance weight-based estimate) for that case, not
treat None as an error.
"""

import os
import subprocess
import json

BASE = os.path.dirname(os.path.abspath(__file__))
EXIFTOOL = os.path.join(BASE, "tools", "exiftool-13.59_64", "exiftool.exe")

# Sensor width in mm, by camera model string as ExifTool reports it. Only
# cameras actually confirmed in use this business's capture files are
# listed — an unknown model returns None rather than guessing a sensor size,
# since a wrong sensor width silently produces a wrong real-world size with
# no way to tell it happened.
SENSOR_WIDTHS_MM = {
    "ZV-E10M2": 23.5,  # Sony APS-C (this business's confirmed capture camera)
}


def _run_exiftool(image_path: str) -> dict:
    try:
        result = subprocess.run(
            [EXIFTOOL, "-j", "-FocalLength#", "-FocusDistance2#", "-DigitalZoomRatio#",
             "-Model", "-ImageWidth", "-ImageHeight", image_path],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout)
        return data[0] if data else {}
    except Exception:
        return {}


def estimate_mm_per_pixel(image_path: str) -> dict:
    """Return {"ok": True, "mm_per_pixel": float, "focal_length_mm": ...,
    "focus_distance_m": ..., "sensor_width_mm": ...} when the file has
    enough metadata, or {"ok": False, "reason": str} when it doesn't —
    missing focus distance, missing/unknown sensor model, or a read error
    are all expected, non-exceptional outcomes here, not failures to alert on.
    """
    if not os.path.exists(EXIFTOOL):
        return {"ok": False, "reason": "exiftool binary not found"}
    if not os.path.exists(image_path):
        return {"ok": False, "reason": f"image not found: {image_path}"}

    meta = _run_exiftool(image_path)
    if not meta:
        return {"ok": False, "reason": "could not read metadata"}

    focal_length = meta.get("FocalLength")
    focus_distance = meta.get("FocusDistance2")
    zoom_ratio = meta.get("DigitalZoomRatio") or 1.0
    model = meta.get("Model", "")
    image_width = meta.get("ImageWidth")

    if not focal_length or not focus_distance or not image_width:
        return {"ok": False,
                "reason": f"missing required EXIF field(s) — focal_length={focal_length}, "
                          f"focus_distance={focus_distance}, image_width={image_width} "
                          f"(common on phone-shot batches, which don't record focus distance)"}

    sensor_width_mm = SENSOR_WIDTHS_MM.get(model)
    if sensor_width_mm is None:
        return {"ok": False, "reason": f"unknown sensor width for camera model {model!r} — "
                                       f"add it to SENSOR_WIDTHS_MM once confirmed, don't guess"}

    focus_distance_mm = float(focus_distance) * 1000.0
    optical_real_width_mm = (sensor_width_mm * focus_distance_mm) / float(focal_length)
    # Digital zoom crops the sensor then upscales back to full resolution —
    # the SAVED image's field of view is narrower than the optical
    # calculation alone implies, by exactly the zoom ratio.
    actual_real_width_mm = optical_real_width_mm / float(zoom_ratio)
    mm_per_pixel = actual_real_width_mm / float(image_width)

    return {
        "ok": True,
        "mm_per_pixel": round(mm_per_pixel, 5),
        "focal_length_mm": focal_length,
        "focus_distance_m": focus_distance,
        "digital_zoom_ratio": zoom_ratio,
        "sensor_width_mm": sensor_width_mm,
        "camera_model": model,
    }


# The tag we read the SKU/label from — confirmed physical size, printed
# consistently by the same supplier for every piece (2026-08-02). Every
# capture shows 2-3 tags per piece but this is specifically the one used for
# the label read, so it's the one with a known fixed size to calibrate on.
TAG_WIDTH_MM = 26.0
TAG_HEIGHT_MM = 19.0
_TAG_ASPECT = TAG_WIDTH_MM / TAG_HEIGHT_MM  # ~1.368


def find_all_tag_rects(image_path: str, aspect_tolerance: float = 0.18) -> list:
    """Every piece has 2-3 tags (label + QR + sometimes a duplicate), often
    folded/overlapping in the frame. Returns ALL rectangles matching the
    tag's aspect ratio, not just the largest — masking only one leaves the
    others' pixels free to bleed into a jewellery bbox as a false positive
    (confirmed directly on LC22_2.jpg, 2026-08-02: a second overlapping tag
    flap inflated the pendant's measured size by ~2x)."""
    import cv2

    img = cv2.imread(image_path)
    if img is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    found = []
    for c in contours:
        if cv2.contourArea(c) < 0.001 * gray.size:
            continue
        rect = cv2.minAreaRect(c)
        (_, _), (w, h), angle = rect
        if w < 5 or h < 5:
            continue
        long_side, short_side = max(w, h), min(w, h)
        aspect = long_side / short_side
        if abs(aspect - _TAG_ASPECT) / _TAG_ASPECT > aspect_tolerance:
            continue
        found.append({
            "width_px": long_side, "height_px": short_side,
            "angle": angle, "area": long_side * short_side,
            "box": cv2.boxPoints(rect).tolist(),
        })
    return found


def find_tag_rect(image_path: str, aspect_tolerance: float = 0.18) -> dict:
    """Locate the label tag by shape: a bright, roughly-rectangular card
    against the black velvet background, with an aspect ratio matching the
    known tag dimensions. Returns {"ok": True, "width_px": float,
    "height_px": float, "box": [(x,y)*4], "angle": float} for the largest
    matching candidate, or {"ok": False, "reason": str}.

    Uses a rotated min-area rectangle (not an axis-aligned bbox) so an
    in-plane-rotated tag still measures its true edge lengths correctly.
    Does NOT correct for out-of-plane tilt/perspective — a tag photographed
    at a steep angle will under-measure one axis; this is a known
    approximation, not a full homography correction.

    Returns only the LARGEST matching rectangle — use find_all_tag_rects()
    instead when you need to exclude every tag-like region (e.g. isolating
    the jewellery itself), since real photos have 2-3 tags and masking only
    the largest lets the others bleed into whatever you're measuring.
    """
    candidates = find_all_tag_rects(image_path, aspect_tolerance)
    if not candidates:
        return {"ok": False, "reason": "no rectangle matching the tag's aspect ratio found"}
    best = max(candidates, key=lambda r: r["area"])
    return {"ok": True, **best}


def _region_sharpness(gray, bbox) -> float:
    """Laplacian-variance sharpness of a crop — same metric app.py's
    BLUR_LAPLACIAN_MIN uses, reused here to compare focus, not blur/reject."""
    import cv2
    x0, y0, x1, y1 = [int(v) for v in bbox]
    crop = gray[max(0, y0):y1, max(0, x0):x1]
    if crop.size < 100:
        return 0.0
    return float(cv2.Laplacian(crop, cv2.CV_64F).var())


def estimate_mm_per_pixel_from_tag(image_path: str, jewellery_bbox: tuple = None) -> dict:
    """Universal calibration — works regardless of which camera/phone took
    the photo, unlike estimate_mm_per_pixel() which needs Sony-specific
    MakerNote fields. Returns {"ok": True, "mm_per_pixel": float, ...} or
    {"ok": False, "reason": str} when no tag-shaped rectangle was found.

    IMPORTANT ASSUMPTION AND ITS LIMIT: this only gives the jewellery's true
    size if the tag and jewellery are roughly the same distance from the
    camera — a hand-held photo can easily hold the tag closer or farther
    than the piece itself, which silently breaks the pixel-ratio transfer
    (perspective makes a nearer object read as more pixels-per-mm than a
    farther one at the same real size). There's no way to fully correct for
    this from a single 2D photo without real depth data, but passing
    jewellery_bbox lets this at least FLAG the risk: a shallow-depth-of-field
    macro shot usually shows a measurable sharpness difference between two
    objects at meaningfully different distances, so comparable sharpness is
    at least evidence the assumption is safe here, not proof of it — treat
    "uncertain_depth" as a real caveat, not a rounding error.
    """
    tag = find_tag_rect(image_path)
    if not tag.get("ok"):
        return tag

    # long_side/width_px measures the tag's real WIDTH edge (26mm),
    # short_side/height_px measures its real HEIGHT edge (19mm) — average
    # the two independent estimates rather than trust one axis alone.
    mmpp_from_width = TAG_WIDTH_MM / tag["width_px"]
    mmpp_from_height = TAG_HEIGHT_MM / tag["height_px"]
    mm_per_pixel = (mmpp_from_width + mmpp_from_height) / 2
    axis_agreement = abs(mmpp_from_width - mmpp_from_height) / mm_per_pixel

    result = {
        "ok": True,
        "mm_per_pixel": round(mm_per_pixel, 5),
        "tag_width_px": round(tag["width_px"], 1),
        "tag_height_px": round(tag["height_px"], 1),
        "axis_agreement_ratio": round(axis_agreement, 3),
        "depth_confidence": "not_checked",
    }

    if jewellery_bbox is not None:
        import cv2
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        xs = [p[0] for p in tag["box"]]
        ys = [p[1] for p in tag["box"]]
        tag_bbox = (min(xs), min(ys), max(xs), max(ys))
        tag_sharpness = _region_sharpness(gray, tag_bbox)
        jewel_sharpness = _region_sharpness(gray, jewellery_bbox)
        if tag_sharpness > 1 and jewel_sharpness > 1:
            ratio = max(tag_sharpness, jewel_sharpness) / min(tag_sharpness, jewel_sharpness)
            result["depth_confidence"] = "same_depth_likely" if ratio < 2.5 else "uncertain_depth"
            result["sharpness_ratio"] = round(ratio, 2)
        else:
            result["depth_confidence"] = "unknown"

    return result


def estimate_object_size_mm(image_path: str, pixel_bbox: tuple) -> dict:
    """pixel_bbox = (x0, y0, x1, y1) of the jewellery's segmented footprint
    in the SAME image estimate_mm_per_pixel was computed from. Returns
    {"ok": True, "width_mm": float, "height_mm": float} or {"ok": False,
    "reason": str} — propagates estimate_mm_per_pixel's failure reason
    unchanged so callers see exactly why (missing metadata vs unknown
    camera), not a generic failure.
    """
    calib = estimate_mm_per_pixel(image_path)
    if not calib.get("ok"):
        return calib

    x0, y0, x1, y1 = pixel_bbox
    mmpp = calib["mm_per_pixel"]
    return {
        "ok": True,
        "width_mm": round((x1 - x0) * mmpp, 1),
        "height_mm": round((y1 - y0) * mmpp, 1),
        "mm_per_pixel": mmpp,
    }
