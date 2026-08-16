"""Turns a recorded turntable-rotation video into multi-angle stills, an
interactive 360 spin viewer's frame set, and a cleaned/cropped 360 video.

Runs entirely locally (ffmpeg + OpenCV) — no AI credit spend, no external
API calls — so it's kicked off synchronously in a background thread right
after the phone uploads the clip, rather than joining the AI-generation
processing queue (see processing_worker.py's docstring for that queue's
actual purpose: gating paid generation calls).

Background isolation assumes a controlled, plain white/near-white light-box
background (per the turntable setup) — a fast brightness/saturation
threshold crop, not sam_locate.py's SAM2 object localisation, since running
a heavy per-frame ML pass across ~24 frames per item would be far slower
for no real accuracy gain in this specific, controlled setup. If the
light-box background ever becomes inconsistent (patterned, coloured,
shadowed), this crop will need revisiting — it is not general-purpose
background removal.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import subprocess

import cv2
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
FRAME_COUNT = 24
CROP_MARGIN_FRACTION = 0.06  # padding added around the detected item bounding box
# Near-white / low-saturation pixels are treated as background. A real
# light-box wall is much closer to pure white than any gold/gem surface,
# so this threshold is deliberately generous rather than tuned per-lighting.
BACKGROUND_VALUE_MIN = 225
BACKGROUND_SATURATION_MAX = 30

_log = logging.getLogger("spin_processor")


class SpinProcessingError(Exception):
    pass


def _find_ffmpeg() -> str:
    """Resolves the ffmpeg binary. Prefers a local, gitignored install under
    tools/ffmpeg/ (see tools/setup_ffmpeg.ps1) over relying on PATH, since a
    fresh PC won't have ffmpeg installed system-wide by default."""
    local_glob = os.path.join(BASE, "tools", "ffmpeg", "**", "bin", "ffmpeg.exe")
    matches = glob.glob(local_glob, recursive=True)
    if matches:
        return matches[0]
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise SpinProcessingError(
        "ffmpeg not found -- run tools/setup_ffmpeg.ps1 once to install it locally, "
        "or install ffmpeg and ensure it's on PATH."
    )


def _probe_duration_seconds(ffmpeg_path: str, video_path: str) -> float:
    result = subprocess.run(
        [ffmpeg_path, "-i", video_path],
        capture_output=True, text=True, timeout=30,
    )
    # ffmpeg writes probe info to stderr and exits non-zero when given no
    # output target -- that's expected here, we only want the logged duration.
    for line in result.stderr.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            timestamp = line.split(",")[0].replace("Duration:", "").strip()
            hours, minutes, seconds = timestamp.split(":")
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise SpinProcessingError(f"Could not read video duration from {video_path}")


def _extract_frames(ffmpeg_path: str, video_path: str, out_dir: str, count: int) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    duration = _probe_duration_seconds(ffmpeg_path, video_path)
    if duration <= 0:
        raise SpinProcessingError(f"Zero-length video: {video_path}")
    fps = count / duration
    pattern = os.path.join(out_dir, "raw_%02d.jpg")
    result = subprocess.run(
        [ffmpeg_path, "-y", "-i", video_path, "-vf", f"fps={fps}", "-frames:v", str(count), pattern],
        capture_output=True, text=True, timeout=120,
    )
    frames = sorted(glob.glob(os.path.join(out_dir, "raw_*.jpg")))
    if not frames:
        raise SpinProcessingError(f"ffmpeg produced no frames: {result.stderr[-500:]}")
    return frames


def _isolate_bounds(bgr: np.ndarray) -> tuple[int, int, int, int] | None:
    """Returns (x0, y0, x1, y1) of the largest non-background contour, or
    None if nothing distinguishable from the background was found."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    value, saturation = hsv[..., 2], hsv[..., 1]
    background = (value >= BACKGROUND_VALUE_MIN) & (saturation <= BACKGROUND_SATURATION_MAX)
    foreground = (~background).astype(np.uint8) * 255
    # Close small gaps (specular highlights on the item that briefly read as
    # "background") before finding the outer contour.
    kernel = np.ones((9, 9), np.uint8)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 200:  # noise floor
        return None
    x, y, w, h = cv2.boundingRect(largest)
    return x, y, x + w, y + h


def _crop_to_item(frame_path: str, out_path: str, shared_bounds: tuple[int, int, int, int] | None) -> tuple[int, int, int, int] | None:
    bgr = cv2.imread(frame_path)
    if bgr is None:
        raise SpinProcessingError(f"Could not read extracted frame: {frame_path}")
    height, width = bgr.shape[:2]
    bounds = shared_bounds or _isolate_bounds(bgr)
    if bounds is None:
        cv2.imwrite(out_path, bgr)  # fall back to the uncropped frame rather than dropping it
        return None
    x0, y0, x1, y1 = bounds
    margin_x = int((x1 - x0) * CROP_MARGIN_FRACTION) + 4
    margin_y = int((y1 - y0) * CROP_MARGIN_FRACTION) + 4
    x0, y0 = max(0, x0 - margin_x), max(0, y0 - margin_y)
    x1, y1 = min(width, x1 + margin_x), min(height, y1 + margin_y)
    cv2.imwrite(out_path, bgr[y0:y1, x0:x1])
    return x0, y0, x1, y1


def _widest_common_crop(bounds_list: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    """A single crop box padded to cover every frame's detected item bounds,
    used for the 360 video so the crop doesn't jump/jitter frame to frame."""
    x0 = min(b[0] for b in bounds_list)
    y0 = min(b[1] for b in bounds_list)
    x1 = max(b[2] for b in bounds_list)
    y1 = max(b[3] for b in bounds_list)
    return x0, y0, x1, y1


def process_spin(video_path: str, output_dir: str, tag_stem: str, frame_count: int = FRAME_COUNT) -> dict:
    """Extracts frame_count evenly-spaced, background-cropped stills into
    output_dir/<tag_stem>_360/frame_NN.jpg, and a cropped/looped 360 video
    at output_dir/<tag_stem>_360.mp4. Returns a manifest dict; raises
    SpinProcessingError on failure (caller decides how to surface/log it --
    this is a cheap, retryable local operation, not an AI credit spend, so
    there's no need for the full pipeline_queue reject/requeue machinery)."""
    ffmpeg_path = _find_ffmpeg()
    frames_dir = os.path.join(output_dir, f"{tag_stem}_360")
    os.makedirs(frames_dir, exist_ok=True)

    raw_dir = os.path.join(frames_dir, "_raw")
    raw_frames = _extract_frames(ffmpeg_path, video_path, raw_dir, frame_count)

    saved_paths: list[str] = []
    bounds_list: list[tuple[int, int, int, int]] = []
    for index, raw_frame in enumerate(raw_frames, start=1):
        out_path = os.path.join(frames_dir, f"frame_{index:02d}.jpg")
        bounds = _crop_to_item(raw_frame, out_path, None)
        saved_paths.append(out_path)
        if bounds:
            bounds_list.append(bounds)
    shutil.rmtree(raw_dir, ignore_errors=True)

    if not bounds_list:
        _log.warning("spin_processor: no clean background separation found for %s -- frames saved uncropped", tag_stem)

    video_out = os.path.join(output_dir, f"{tag_stem}_360.mp4")
    if bounds_list:
        crop_x0, crop_y0, crop_x1, crop_y1 = _widest_common_crop(bounds_list)
        crop_w, crop_h = crop_x1 - crop_x0, crop_y1 - crop_y0
        crop_filter = f"crop={crop_w}:{crop_h}:{crop_x0}:{crop_y0}"
        subprocess.run(
            [ffmpeg_path, "-y", "-i", video_path, "-vf", crop_filter,
             "-an", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", video_out],
            capture_output=True, text=True, timeout=180,
        )
    else:
        shutil.copyfile(video_path, video_out) if os.path.exists(video_path) else None

    manifest = {"tag": tag_stem, "frame_count": len(saved_paths), "frames": [os.path.basename(p) for p in saved_paths]}
    with open(os.path.join(frames_dir, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    return manifest
