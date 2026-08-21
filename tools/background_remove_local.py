"""Offline, non-destructive jewellery background removal.

Uses only model weights already cached on this PC. Source files are never
modified. Results preserve the source dimensions and relative folder layout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import cv2
import numpy as np
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ornament_code_map as ocm  # noqa: E402
import sam_locate  # noqa: E402


PAIRED_CATEGORIES = frozenset({
    "bali_18", "bali_22", "tops_18", "tops_22", "dull_22",
    "earring_22", "jhumka_22", "kaan_chain_22",
})
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})


def category_for(path: Path, source_root: Path) -> str | None:
    try:
        folder = path.relative_to(source_root).parts[0]
    except (ValueError, IndexError):
        folder = path.parent.name
    normalized = re.sub(r"^\s*\d+\s*", "", folder).strip().casefold()
    for category in ocm.CATEGORIES:
        if category.label.casefold() == normalized:
            return category.key
    from_code = ocm.category_from_tag_code(path.stem)
    return from_code.key if from_code else None


def read_bgr(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        rgb = np.asarray(image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def mask_quality(mask: np.ndarray, expected: int, component_masks: list[np.ndarray]) -> tuple[bool, str]:
    height, width = mask.shape
    coverage = float(mask.sum()) / float(height * width)
    if coverage < 0.0005:
        return False, f"mask_too_small:{coverage:.5f}"
    if coverage > 0.35:
        return False, f"mask_too_large:{coverage:.3f}"
    if len(component_masks) < expected:
        return False, f"pieces_missing:{len(component_masks)}/{expected}"
    ys, xs = np.nonzero(mask)
    if len(xs) < 100:
        return False, "mask_has_too_few_pixels"
    bbox_area = (int(xs.max()) - int(xs.min()) + 1) * (int(ys.max()) - int(ys.min()) + 1)
    if bbox_area / float(height * width) > 0.75:
        return False, "mask_bbox_spans_most_of_frame"
    return True, "ok"


def remove_background(source: Path, destination: Path, source_root: Path, engine: str) -> dict:
    started = time.perf_counter()
    category = category_for(source, source_root)
    expected = 2 if category in PAIRED_CATEGORIES else 1
    bgr = read_bgr(source)
    height, width = bgr.shape[:2]

    if engine == "sam3":
        boxes, raw_masks = sam_locate._sam3_boxes_and_masks(
            bgr, expect=expected, category=category
        )
    else:
        boxes = sam_locate._locate_sam2(bgr, expect=expected, margin=0.04)
        raw_masks = list(sam_locate._last_masks)
    refined_masks: list[np.ndarray] = []
    for raw_mask in raw_masks:
        if raw_mask is None or raw_mask.shape != (height, width):
            continue
        refined = sam_locate._refine_mask(bgr, raw_mask, category)
        if int(refined.sum()) >= 200:
            refined_masks.append(refined)

    union = np.zeros((height, width), dtype=bool)
    for refined in refined_masks:
        union |= refined
    accepted, reason = mask_quality(union, expected, refined_masks)
    result = {
        "source": str(source),
        "destination": str(destination),
        "category": category,
        "engine": engine,
        "expected_pieces": expected,
        "boxes": [list(map(int, box)) for box in boxes],
        "masks": len(refined_masks),
        "coverage": round(float(union.sum()) / float(height * width), 6),
        "status": "written" if accepted else "rejected",
        "reason": reason,
    }
    if not accepted:
        result["seconds"] = round(time.perf_counter() - started, 3)
        return result

    # One-pixel feather: antialiased edge without recolouring or smoothing
    # jewellery pixels. Everything outside the semantic mask becomes #FFFFFF.
    composited = sam_locate._composite_on_white(bgr, union, feather=1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + ".tmp" + destination.suffix)
    if not cv2.imwrite(str(temporary), composited, [cv2.IMWRITE_JPEG_QUALITY, 96]):
        raise RuntimeError(f"failed to write {temporary}")
    with Image.open(temporary) as check:
        if check.size != (width, height) or check.format != "JPEG":
            raise RuntimeError(f"output verification failed: {temporary}")
        check.verify()
    os.replace(temporary, destination)
    result["seconds"] = round(time.perf_counter() - started, 3)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--source-root", type=Path, default=ROOT / "capture_intake")
    parser.add_argument("--output-root", type=Path, default=ROOT / "background_removed")
    parser.add_argument("--engine", choices=("sam3", "sam2"), default="sam3")
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    report_dir = ROOT / "reports" / "background_removal"
    report_dir.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        for supplied in args.sources:
            source = supplied.resolve()
            if source.suffix.casefold() not in IMAGE_SUFFIXES:
                raise ValueError(f"unsupported image: {source}")
            relative = source.relative_to(source_root)
            destination = (output_root / relative).with_suffix(".jpg")
            result = remove_background(source, destination, source_root, args.engine)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        sam_locate.release()
    report = report_dir / "pilot_results.json"
    report.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if all(item["status"] == "written" for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
