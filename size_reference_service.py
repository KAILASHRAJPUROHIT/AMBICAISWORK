"""
size_reference_service.py — background scanner that pre-computes a real-world
size estimate for every item in capture_intake, so the tool already has a
grounded size reference by the time that item is actually processed for
generation, instead of computing it on the hot path.

Per item, combines two independent signals into one candidate, per the user's
explicit direction (2026-08-02) not to rely on either alone:
  1. Tag-based photogrammetry (jewellery_localization + photogrammetry) — a
     direct, item-specific measurement using the known 26mm x 19mm label tag
     as an in-frame ruler. Strong signal when depth_confidence says the tag
     and jewellery are plausibly at the same distance from the camera; weak
     signal (flagged, not discarded) otherwise.
  2. Web search for the style/category's typical published size — a coarse,
     noisy category average, never an exact match for one specific piece,
     but useful as a sanity bound: if the tag measurement is wildly outside
     what real jewellery of this style normally measures, that discrepancy
     itself is a real, actionable flag (this is exactly what caught
     LC22_11's ~11cm measured pendant against a ~6cm published reference).

Combination rule: prefer the tag measurement when depth_confidence is
"same_depth_likely"; otherwise report both and flag "verify" rather than
silently pick one — an unresolved disagreement should reach a human, not
get averaged away.

Results are cached forever per source file path + mtime in
size_references.json — rerunning this script only processes files that are
new or have changed since the last scan.
"""

import json
import os
import re
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE, "data", "size_references.json")
CAPTURE_INTAKE_DIR = os.path.join(BASE, "capture_intake")
_lock = threading.Lock()


def _load_cache() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
    os.replace(tmp, CACHE_PATH)


def _category_from_folder(folder_name: str) -> str:
    """Best-effort category guess from the capture_intake subfolder name
    (e.g. "40 LOCKET 22" -> "locket_22", "10 EARRING 22" -> "earrings").
    Falls back to a lowercased, underscored version of the raw folder name
    when no known mapping matches — better than crashing on an unrecognized
    folder, and callers already treat unknown categories as "no zone
    guidance available" gracefully."""
    name = folder_name.lower()
    if "locket" in name:
        return "locket_22"
    if "earring" in name or "jhumka" in name or "tops" in name:
        return "earrings"
    if "ring" in name and "gent" in name:
        return "gents_rings"
    if "ring" in name:
        return "ladies_rings"
    if "bali" in name:
        return "ladies_bali"
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


def compute_reference(image_path: str, category: str) -> dict:
    """Run localization + tag-calibration + web search for one item. Returns
    a result dict suitable for storing in the cache — never raises, always
    returns SOME dict describing what happened (ok or a reason string),
    since a failure on one item must not stop the whole background scan."""
    import jewellery_localization as jl
    import photogrammetry as pg
    import web_size_reference as wsr

    result = {"computed_at": time.time(), "ok": False}

    loc = jl.locate_jewellery_bbox(image_path)
    if not loc.get("ok"):
        result["reason"] = f"localization failed: {loc.get('reason')}"
        return result

    calib = pg.estimate_mm_per_pixel_from_tag(image_path, jewellery_bbox=loc["bbox"])
    if not calib.get("ok"):
        result["reason"] = f"tag calibration failed: {calib.get('reason')}"
        return result

    x0, y0, x1, y1 = loc["bbox"]
    measured_width_mm = round((x1 - x0) * calib["mm_per_pixel"], 1)
    measured_height_mm = round((y1 - y0) * calib["mm_per_pixel"], 1)
    depth_confidence = calib.get("depth_confidence", "not_checked")

    web = wsr.search_size_reference(category)

    candidate = {
        "measured_width_mm": measured_width_mm,
        "measured_height_mm": measured_height_mm,
        "depth_confidence": depth_confidence,
        "web_reference_mm": web.get("median_mm") if web.get("ok") else None,
        "web_sources": web.get("sources", []) if web.get("ok") else [],
    }

    if depth_confidence == "same_depth_likely":
        candidate["strong_candidate_mm"] = measured_height_mm
        candidate["confidence"] = "high"
    else:
        # Depth is uncertain — try the learned correction (built from real
        # ground-truth measurements, see depth_correction.py) before falling
        # back to the web-reference cross-check or giving up.
        import depth_correction as dcorr
        corrected = dcorr.apply_correction(measured_height_mm)
        working_value = corrected["corrected_mm"] if corrected.get("ok") else measured_height_mm

        if corrected.get("ok"):
            candidate["depth_corrected_mm"] = corrected["corrected_mm"]
            candidate["correction_factor_used"] = corrected["factor_used"]
            candidate["correction_n"] = corrected["n"]

        if web.get("ok") and web["median_mm"] > 0:
            ratio = working_value / web["median_mm"]
            if 0.5 <= ratio <= 2.0:
                candidate["strong_candidate_mm"] = working_value
                candidate["confidence"] = (
                    f"medium — depth-corrected (factor {corrected['factor_used']}x, "
                    f"n={corrected['n']}{', provisional' if corrected.get('provisional') else ''}), "
                    f"corroborated by web reference"
                    if corrected.get("ok") else
                    "medium — corroborated by web reference (no depth correction available yet)"
                )
            else:
                candidate["strong_candidate_mm"] = None
                candidate["confidence"] = (
                    f"low — measurement ({working_value}mm) disagrees with web "
                    f"reference ({web['median_mm']}mm) by {ratio:.1f}x; verify manually"
                )
        elif corrected.get("ok"):
            candidate["strong_candidate_mm"] = working_value
            candidate["confidence"] = (
                f"medium — depth-corrected (factor {corrected['factor_used']}x from "
                f"{corrected['n']} ground-truth measurement(s)"
                f"{', provisional, needs more ground truth' if corrected.get('provisional') else ''})"
            )
        else:
            candidate["strong_candidate_mm"] = measured_height_mm
            candidate["confidence"] = (
                "low — depth uncertain, no correction data or web reference available yet"
            )

    result.update(ok=True, **candidate)
    return result


def scan_capture_intake(limit: int = None, on_progress=None) -> dict:
    """Walk capture_intake, compute a size reference for every image not
    already cached (by path+mtime), skip everything else. Returns a summary
    {"processed": int, "skipped_cached": int, "failed": int}."""
    cache = _load_cache()
    processed = skipped = failed = 0

    if not os.path.isdir(CAPTURE_INTAKE_DIR):
        return {"processed": 0, "skipped_cached": 0, "failed": 0,
                "error": f"capture_intake not found at {CAPTURE_INTAKE_DIR}"}

    for root, dirs, files in os.walk(CAPTURE_INTAKE_DIR):
        if "_tag_archive" in root:
            continue
        folder_name = os.path.basename(root)
        category = _category_from_folder(folder_name)

        for fname in files:
            if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            path = os.path.join(root, fname)
            key = os.path.relpath(path, BASE).replace("\\", "/")
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue

            cached = cache.get(key)
            if cached and cached.get("_mtime") == mtime:
                skipped += 1
                continue

            if limit is not None and processed >= limit:
                continue

            result = compute_reference(path, category)
            result["_mtime"] = mtime
            result["_category"] = category
            with _lock:
                cache[key] = result
                _save_cache(cache)

            if result.get("ok"):
                processed += 1
            else:
                failed += 1

            if on_progress:
                on_progress(key, result)

    return {"processed": processed, "skipped_cached": skipped, "failed": failed}


def get_reference(image_path: str) -> dict:
    """Look up an already-computed size reference for an item by path.
    Returns {"ok": False, "reason": "not yet computed"} if the background
    scan hasn't reached this file yet — callers must treat that as
    'no size guidance available', not an error."""
    cache = _load_cache()
    key = os.path.relpath(os.path.abspath(image_path), BASE).replace("\\", "/")
    result = cache.get(key)
    if result is None:
        return {"ok": False, "reason": "not yet computed"}
    return result


def run_background_loop(poll_interval_s: int = 300):
    """Continuously rescan capture_intake for new/changed items. Intended to
    run as a standalone long-lived process (py -3.11 size_reference_service.py),
    separate from the main app.py — this does real API calls (Gemini
    localization, web search) per new item and should not block request
    handling in the main Flask process."""
    print(f"[size_reference_service] watching {CAPTURE_INTAKE_DIR}, polling every {poll_interval_s}s",
          flush=True)

    count = [0]

    def _log_progress(key, result):
        count[0] += 1
        if result.get("ok"):
            size = result.get("strong_candidate_mm")
            conf = result.get("confidence", "")
            print(f"[size_reference_service] #{count[0]} {key}: "
                  f"{size}mm ({conf})" if size else f"[size_reference_service] #{count[0]} {key}: "
                  f"no strong candidate ({conf})", flush=True)
        else:
            print(f"[size_reference_service] #{count[0]} {key}: FAILED — {result.get('reason')}", flush=True)

    while True:
        summary = scan_capture_intake(on_progress=_log_progress)
        print(f"[size_reference_service] scan pass complete: {summary}", flush=True)
        time.sleep(poll_interval_s)


if __name__ == "__main__":
    run_background_loop()
