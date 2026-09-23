"""Regression hardwall for the owner-approved three-angle compositor.

The visual contract is deliberate. Refactors may improve internals, but may
not change panel order, 60/20/20 area weighting, source-pixel preservation,
JPEG chroma sampling, or atomic publication without explicit owner approval.
"""

from pathlib import Path
import math

from PIL import Image, JpegImagePlugin

import capture_tool


def _near(actual, expected, tolerance=12):
    return all(abs(a - e) <= tolerance for a, e in zip(actual, expected))


def test_approved_three_angle_layout_is_locked(tmp_path):
    # Equal 120x80 sources make the approved geometry deterministic:
    # MAIN scales to three area units; each side remains one area unit.
    source_size = (120, 80)
    main = tmp_path / "main.png"
    left = tmp_path / "angle1.png"
    right = tmp_path / "angle2.png"
    output = tmp_path / "TAG.jpg"
    Image.new("RGB", source_size, (220, 20, 20)).save(main)
    Image.new("RGB", source_size, (20, 220, 20)).save(left)
    Image.new("RGB", source_size, (20, 20, 220)).save(right)

    assert capture_tool.stitch_angles(str(main), str(left), str(right), str(output))
    assert output.is_file()
    assert not Path(f"{output}.composite.tmp.jpg").exists()

    with Image.open(output) as composite:
        composite.load()
        # Approved constants and ceil(sqrt(3)) hero scaling produce this
        # exact canvas. Any dimension drift means layout geometry changed.
        assert composite.size == (384, 543)
        assert composite.format == "JPEG"
        assert JpegImagePlugin.get_sampling(composite) == 0  # 4:4:4

        # Semantic panel order: MAIN/top, ANGLE_1/left, ANGLE_2/right.
        assert _near(composite.getpixel((192, 100)), (220, 20, 20))
        assert _near(composite.getpixel((108, 365)), (20, 220, 20))
        assert _near(composite.getpixel((276, 365)), (20, 20, 220))


def test_approved_area_ratio_and_no_downscale_are_locked():
    source = Image.new("RGB", (120, 80), (1, 2, 3))
    source_area = source.width * source.height
    side = capture_tool._stitch_scale_to_area(source, source_area)
    hero = capture_tool._stitch_scale_to_area(source, source_area * 3)

    total = hero.width * hero.height + 2 * side.width * side.height
    hero_fraction = hero.width * hero.height / total
    side_fraction = side.width * side.height / total
    assert math.isclose(hero_fraction, 0.60, abs_tol=0.002)
    assert math.isclose(side_fraction, 0.20, abs_tol=0.002)

    # Even an invalid smaller target cannot throw away source pixels.
    assert capture_tool._stitch_scale_to_area(source, 1).size == source.size
