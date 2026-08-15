"""
depth_correction.py — a learned correction factor for tag-based size
measurements flagged "uncertain_depth" (photogrammetry.py), built from real
ground-truth measurements the user provides.

Why this exists, and its real limitation: tag-based calibration assumes the
tag and jewellery are at the same distance from the camera. When they
aren't (confirmed real case, 2026-08-02: LC22_2.jpg, tag held closer than
the pendant), the measurement is systematically wrong — that photo measured
14.3mm against a real, ruler-measured 24mm, a ~1.68x undersize error.

A rigorous depth-from-defocus correction needs known aperture, focal length,
and absolute focus distance — phone captures (the exact case this problem
shows up in) don't record any of that in EXIF (confirmed: device "A069P"
has no distance data at all). Without that physics, this can't be a real
optical model — it's a learned empirical correction, only as good as the
ground-truth measurements behind it. Documented plainly rather than
disguised as more rigorous than it is.

With n=1 ground-truth point, correction_factor() returns that single ratio.
As more real measurements accumulate (via record_ground_truth), it becomes
a proper average — call it what it is: a small, growing calibration
dataset, not a formula.
"""

import json
import os
import statistics

BASE = os.path.dirname(os.path.abspath(__file__))
GROUND_TRUTH_PATH = os.path.join(BASE, "data", "depth_correction_ground_truth.jsonl")


def record_ground_truth(image_path: str, measured_mm: float, real_mm: float,
                        sharpness_ratio: float = None, note: str = "") -> None:
    """Log one real, physically-measured ground truth against what the
    tag-calibration pipeline computed for the same photo. This is the ONLY
    way the correction factor improves — it does not guess or extrapolate
    beyond what's actually been measured and recorded."""
    record = {
        "image_path": image_path,
        "measured_mm": measured_mm,
        "real_mm": real_mm,
        "correction_ratio": round(real_mm / measured_mm, 4) if measured_mm else None,
        "sharpness_ratio": sharpness_ratio,
        "note": note,
    }
    with open(GROUND_TRUTH_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _load_ground_truth() -> list:
    if not os.path.exists(GROUND_TRUTH_PATH):
        return []
    records = []
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def correction_factor() -> dict:
    """Return {"ok": True, "factor": float, "n": int, "std_dev": float|None}
    — the mean correction ratio (real_mm / measured_mm) across all recorded
    ground truth, or {"ok": False, "reason": str} if none recorded yet.
    std_dev is None until n >= 2 — with a single data point there is no
    variance to report, and callers should treat a single-point factor as
    provisional (this is surfaced explicitly, not hidden)."""
    records = [r for r in _load_ground_truth() if r.get("correction_ratio")]
    if not records:
        return {"ok": False, "reason": "no ground truth recorded yet"}

    ratios = [r["correction_ratio"] for r in records]
    factor = statistics.mean(ratios)
    std_dev = statistics.stdev(ratios) if len(ratios) >= 2 else None
    return {"ok": True, "factor": round(factor, 3), "n": len(ratios),
            "std_dev": round(std_dev, 3) if std_dev is not None else None,
            "provisional": len(ratios) < 5}


def apply_correction(measured_mm: float) -> dict:
    """Apply the learned correction to a depth-uncertain measurement.
    Returns {"ok": True, "corrected_mm": float, "factor_used": float, "n": int,
    "provisional": bool} or {"ok": False, "reason": str} when no ground
    truth exists yet — callers must fall back to the uncorrected value (or
    to the web-search cross-check) in that case, not invent a factor."""
    cf = correction_factor()
    if not cf.get("ok"):
        return cf
    return {
        "ok": True,
        "corrected_mm": round(measured_mm * cf["factor"], 1),
        "factor_used": cf["factor"],
        "n": cf["n"],
        "provisional": cf["provisional"],
    }
