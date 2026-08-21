"""Deterministic camera-photo -> studio-white catalogue plate.

Conforms to this project's existing measurable standards instead of inventing
its own look:
  - jewellery_image_policy: square frame, item fills 75-90% along the
    dominant dimension, >=5% margin to every edge, perfectly level, soft
    contact shadow directly beneath (plain-white "Studio Mode White" style).
  - color_standardize: the approved gold-finish chain
    (remove_reflection_artifacts -> add_shine -> standardize_gold), reused
    unmodified so plates match the FLUX-delivered catalogue look. The only
    addition here is seeding its internal RNG so the micro-grain in
    add_shine is repeatable run-to-run.
  - output is written at high resolution; pass --delivery to additionally
    emit the official 2400x2400 sRGB/72dpi <=1MB file via image_spec.

Stages (all deterministic pixel maths, no generative model):
  1. rembg/u2net subject mask (fixed cached weights, CPU inference).
  2. White-patch white balance from the OLD background pixels (capped gains),
     then levels stretch on item luminance -> bright neutral studio exposure
     while preserving real specular detail.
  3. Feathered composite on pure #FFFFFF.
  4. Auto-level: PCA tilt from the mask, rotate about the item centroid.
  5. Square canvas centring at --fill occupancy with a soft elliptical
     contact shadow under the item.
  6. Project gold-finish chain (color_standardize), seeded for determinism.
  7. Frame verified with jewellery_image_policy.evaluate_studio_bbox.

Source files are never modified. Outputs land in --out-dir/<stem>/.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from rembg import new_session, remove

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jewelry_policy_shim_placeholder if False else None  # noqa
import color_standardize  # noqa: E402
import jewellery_image_policy as policy  # noqa: E402

# add_shine draws micro-grain via np.random.default_rng() unseeded; pin it so
# plates are byte-identical run-to-run.
_rng_factory = np.random.default_rng
color_standardize.np.random.default_rng = lambda *a, **k: _rng_factory(20260821)

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})
WHITE = (255, 255, 255)


def read_bgr(path: Path) -> np.ndarray:
    from PIL import ImageOps

    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        rgb = np.asarray(image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def cutout_mask(bgr: np.ndarray, session) -> np.ndarray:
    """Alpha mask of the main subject; keeps components >= 1% of the largest."""
    rgba = remove(bgr, session=session)
    binary = (rgba[:, :, 3] > 127).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if count <= 1:
        return binary
    largest = int(stats[1:, cv2.CC_STAT_AREA].max())
    keep = np.zeros_like(binary)
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] >= max(0.01 * largest, 50):
            keep[labels == i] = 1
    return keep


def measure_tilt(mask: np.ndarray) -> float:
    """PCA major-axis angle in degrees folded into [-45, 45)."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 100:
        return 0.0
    points = np.stack([xs - xs.mean(), ys - ys.mean()]).astype(np.float64)
    eigenvalues, eigenvectors = np.linalg.eigh(np.cov(points))
    major = eigenvectors[:, int(np.argmax(eigenvalues))]
    angle = float(np.degrees(np.arctan2(major[1], major[0]))) % 180.0
    if angle >= 90.0:
        angle -= 180.0
    if angle >= 45.0:
        angle -= 90.0
    elif angle < -45.0:
        angle += 90.0
    return angle


def rotate_expanded(image: np.ndarray, mask: np.ndarray, degrees: float) -> tuple[np.ndarray, np.ndarray]:
    """Rotate image+mask about the item centroid on an expanded canvas, white fill."""
    height, width = image.shape[:2]
    ys, xs = np.nonzero(mask)
    center = (float(xs.mean()), float(ys.mean()))
    matrix = cv2.getRotationMatrix2D(center, degrees, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_size = (int(height * sin + width * cos), int(height * cos + width * sin))
    matrix[0, 2] += new_size[0] / 2 - center[0]
    matrix[1, 2] += new_size[1] / 2 - center[1]
    rotated = cv2.warpAffine(
        image, matrix, new_size, flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=WHITE,
    )
    rotated_mask = cv2.warpAffine(
        mask, matrix, new_size, flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )
    return rotated, rotated_mask


def white_balance_from_background(bgr: np.ndarray, mask: np.ndarray,
                                  gain_cap: float = 1.20) -> np.ndarray:
    """White-patch WB from bright old-background pixels; capped so gold keeps warmth."""
    background = bgr[mask == 0]
    if len(background) < 1000:
        return bgr
    brightness = background.mean(axis=1)
    bright = background[brightness >= np.percentile(brightness, 75)]
    means = bright.mean(axis=0)
    gains = float(means.max()) / np.maximum(means, 1e-6)
    gains = np.clip(gains, 1.0 / gain_cap, gain_cap)
    return np.clip(bgr.astype(np.float32) * gains[None, None, :], 0, 255).astype(np.uint8)


def normalize_levels(bgr: np.ndarray, mask: np.ndarray,
                     low_target: int = 18, high_target: int = 246) -> np.ndarray:
    """Stretch item luminance percentiles (1% -> low_target, 99% -> high_target)."""
    luminance = bgr.mean(axis=2)
    item = luminance[mask > 0]
    if len(item) < 100:
        return bgr
    lo, hi = np.percentile(item, 1.0), np.percentile(item, 99.0)
    if hi - lo < 10:
        return bgr
    scale = (high_target - low_target) / (hi - lo)
    lut = np.clip((np.arange(256, dtype=np.float32) - lo) * scale + low_target, 0, 255)
    return cv2.LUT(bgr, lut.astype(np.uint8))


def composite_on_white(bgr: np.ndarray, mask: np.ndarray, feather: int = 1) -> np.ndarray:
    soft = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), feather)
    alpha = np.clip(soft, 0.0, 1.0)[:, :, None]
    white = np.full_like(bgr, WHITE, dtype=np.uint8)
    return (bgr.astype(np.float32) * alpha + white.astype(np.float32) * (1.0 - alpha)).astype(np.uint8)


def studio_canvas(item: np.ndarray, mask: np.ndarray, fill: float,
                  shadow_opacity: float = 0.16) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]:
    """Centre the levelled item on a square white canvas so its bbox fills
    `fill` of the side (policy window 0.75-0.90), with a soft contact shadow
    directly beneath. Returns canvas, canvas mask, and the item bbox on canvas."""
    height, width = item.shape[:2]
    span = max(width, height)
    side = int(round(span / fill))
    scale = (span * fill / fill) / span  # == 1.0; item is used at native size
    del scale
    ys, xs = np.nonzero(mask)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    bw, bh = x1 - x0, y1 - y0
    # Crop to the item bbox first so centring/fill is measured on the item.
    item_c = item[y0:y1, x0:x1]
    mask_c = mask[y0:y1, x0:x1]

    side = int(round(max(bw, bh) / min(max(fill, 0.51), 0.95)))
    pad_x, pad_y = (side - bw) // 2, (side - bh) // 2
    canvas = np.full((side, side, 3), WHITE, dtype=np.uint8)
    canvas_mask = np.zeros((side, side), dtype=np.uint8)

    shadow = np.zeros((side, side), dtype=np.float32)
    ellipse_w = max(20, int(bw * 0.9))
    ellipse_h = max(12, int(bh * 0.16))
    centre_x, base_y = side // 2, pad_y + bh
    cv2.ellipse(shadow, (centre_x, base_y), (ellipse_w // 2, ellipse_h // 2),
                0.0, 0, 360, 1.0, -1)
    shadow = cv2.GaussianBlur(shadow, (0, 0), max(6, side // 60))
    peak = float(shadow.max())
    if peak > 1e-6:
        canvas = (canvas.astype(np.float32) * (1.0 - (shadow / peak)[:, :, None] * shadow_opacity)).astype(np.uint8)

    canvas[pad_y:pad_y + bh, pad_x:pad_x + bw] = item_c
    canvas_mask[pad_y:pad_y + bh, pad_x:pad_x + bw] = mask_c
    bbox = (pad_x, pad_y, pad_x + bw, pad_y + bh)
    return canvas, canvas_mask, bbox


def apply_gold_finish(canvas_rgb: Image.Image) -> Image.Image:
    """The project's approved deterministic chain, in production order."""
    polished = color_standardize.remove_reflection_artifacts(canvas_rgb)
    polished = color_standardize.add_shine(polished)
    return color_standardize.standardize_gold(polished)


def edit_photo(source: Path, out_dir: Path, session, threshold_deg: float,
               max_rotation_deg: float, fill: float, polish: bool,
               delivery: bool) -> dict:
    started = time.perf_counter()
    bgr = read_bgr(source)

    mask = cutout_mask(bgr, session)
    if int(mask.sum()) < 200:
        raise RuntimeError(f"no usable subject found in {source.name}")

    bgr = white_balance_from_background(bgr, mask)
    bgr = normalize_levels(bgr, mask)
    composited = composite_on_white(bgr, mask)

    angle = measure_tilt(mask)
    applied = 0.0
    if abs(angle) >= threshold_deg:
        applied = float(np.clip(angle, -max_rotation_deg, max_rotation_deg))
        composited, mask = rotate_expanded(composited, mask, applied)

    canvas, canvas_mask, bbox = studio_canvas(composited, mask, fill)

    stem_dir = out_dir / source.stem
    stem_dir.mkdir(parents=True, exist_ok=True)
    edited_path = stem_dir / "edited.jpg"

    if polish:
        canvas_pil = apply_gold_finish(Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)))
        canvas = cv2.cvtColor(np.asarray(canvas_pil), cv2.COLOR_RGB2BGR)

    cv2.imwrite(str(edited_path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 96])

    frame_check = policy.evaluate_studio_bbox((canvas.shape[1], canvas.shape[0]), bbox)

    result = {
        "source": str(source),
        "edited": str(edited_path),
        "tilt_measured_deg": round(angle, 3),
        "rotation_applied_deg": round(applied, 3),
        "output_size_wh": [int(canvas.shape[1]), int(canvas.shape[0])],
        "frame_check": frame_check.as_dict(),
        "seconds": round(time.perf_counter() - started, 3),
    }

    if delivery:
        import image_spec

        delivery_path = stem_dir / "delivery_2400.jpg"
        image_spec.convert_delivery_image(
            str(edited_path), str(delivery_path),
            strategy="pad", overwrite=True,
            maximum_file_bytes=1_000_000, minimum_jpeg_quality=88,
        )
        result["delivery"] = str(delivery_path)

    (stem_dir / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("photo_edit_output"))
    parser.add_argument("--fill", type=float, default=0.85,
                        help="item bbox share of canvas side (policy window 0.75-0.90)")
    parser.add_argument("--threshold-deg", type=float, default=1.0)
    parser.add_argument("--max-rotation-deg", type=float, default=30.0)
    parser.add_argument("--no-polish", action="store_true",
                        help="skip the color_standardize gold-finish chain")
    parser.add_argument("--delivery", action="store_true",
                        help="also emit the official 2400x2400 image_spec JPEG")
    args = parser.parse_args()

    session = new_session("u2net")
    ok = True
    for supplied in args.sources:
        source = supplied.resolve()
        if source.suffix.casefold() not in IMAGE_SUFFIXES:
            print(f"SKIP unsupported image: {source}")
            continue
        try:
            report = edit_photo(source, args.out_dir.resolve(), session,
                                args.threshold_deg, args.max_rotation_deg,
                                args.fill, not args.no_polish, args.delivery)
            print(json.dumps(report, ensure_ascii=False), flush=True)
        except Exception as error:  # noqa: BLE001
            ok = False
            print(f"FAIL {source}: {error}", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
