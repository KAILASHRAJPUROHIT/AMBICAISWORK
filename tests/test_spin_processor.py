"""spin_processor.py exercised against a synthetic clip: a dark square
against a white background, moving across frames to stand in for a rotating
item. Verifies frame extraction + background-crop isolation actually crops
(rather than silently passing the full frame through) and that the 360
video gets produced."""
import json
import os

import cv2
import numpy as np
import pytest

import spin_processor


def _make_synthetic_clip(path: str, frame_count: int = 48, size: int = 240) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, 24, (size, size))
    try:
        for index in range(frame_count):
            frame = np.full((size, size, 3), 250, dtype=np.uint8)  # near-white background
            center = int(size * 0.3 + (size * 0.4) * (index / frame_count))
            cv2.rectangle(frame, (center - 20, size // 2 - 20), (center + 20, size // 2 + 20), (30, 30, 30), -1)
            writer.write(frame)
    finally:
        writer.release()


@pytest.fixture
def synthetic_clip(tmp_path):
    clip_path = str(tmp_path / "spin.mp4")
    _make_synthetic_clip(clip_path)
    return clip_path


def test_ffmpeg_resolves():
    # Skips (rather than fails) on a machine without ffmpeg set up yet --
    # see tools/setup_ffmpeg.ps1 -- this test only confirms the resolver
    # itself works when ffmpeg IS present.
    try:
        path = spin_processor._find_ffmpeg()
    except spin_processor.SpinProcessingError:
        pytest.skip("ffmpeg not installed -- run tools/setup_ffmpeg.ps1")
        return
    assert os.path.isfile(path)


def test_process_spin_extracts_cropped_frames(tmp_path, synthetic_clip):
    try:
        spin_processor._find_ffmpeg()
    except spin_processor.SpinProcessingError:
        pytest.skip("ffmpeg not installed -- run tools/setup_ffmpeg.ps1")
        return

    output_dir = str(tmp_path / "output")
    manifest = spin_processor.process_spin(synthetic_clip, output_dir, "TEST_360", frame_count=12)

    assert manifest["frame_count"] == 12
    frames_dir = os.path.join(output_dir, "TEST_360_360")
    saved = sorted(f for f in os.listdir(frames_dir) if f.startswith("frame_"))
    assert len(saved) == 12

    source_size = os.path.getsize(synthetic_clip)
    cropped_smaller_than_full_frame = False
    for name in saved:
        frame = cv2.imread(os.path.join(frames_dir, name))
        assert frame is not None
        if frame.shape[0] < 240 or frame.shape[1] < 240:
            cropped_smaller_than_full_frame = True
    assert cropped_smaller_than_full_frame, "expected at least one frame to be cropped smaller than the 240x240 source"

    manifest_path = os.path.join(frames_dir, "manifest.json")
    assert os.path.isfile(manifest_path)
    with open(manifest_path, encoding="utf-8") as handle:
        assert json.load(handle)["frame_count"] == 12

    video_out = os.path.join(output_dir, "TEST_360_360.mp4")
    assert os.path.isfile(video_out)
    assert os.path.getsize(video_out) > 0
