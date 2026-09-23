from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

import reference_color_report as report


def _synthetic_plate(path: Path, blue_inside_product: bool) -> None:
    image = np.full((500, 700, 3), 215, dtype=np.uint8)
    # Textured gold product at the centre.
    cv2.rectangle(image, (250, 170), (450, 330), (45, 155, 210), -1)
    for x in range(255, 450, 10):
        cv2.line(image, (x, 170), (x, 330), (20, 90, 150), 2)
    # Sharp blue shop reflection. Its location determines whether it is valid.
    centre = (390, 250) if blue_inside_product else (620, 420)
    cv2.circle(image, centre, 24, (230, 35, 20), -1)
    Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).save(path)


def test_blue_background_is_excluded_from_product_colour(tmp_path, monkeypatch):
    source = tmp_path / "background-blue.jpg"
    _synthetic_plate(source, blue_inside_product=False)
    monkeypatch.setattr(
        report,
        "_product_region_mask",
        lambda arr: (
            np.pad(np.ones((160, 200), dtype=bool), ((170, 170), (250, 250))),
            [[250, 170, 450, 330]],
        ),
    )

    result = report.analyze(str(source))

    assert result["has_colour"] is False
    assert "blue" not in result["prompt_line"].lower()


def test_blue_stone_inside_gold_product_is_preserved(tmp_path, monkeypatch):
    source = tmp_path / "product-blue.jpg"
    _synthetic_plate(source, blue_inside_product=True)
    monkeypatch.setattr(
        report,
        "_product_region_mask",
        lambda arr: (
            np.pad(np.ones((160, 200), dtype=bool), ((170, 170), (250, 250))),
            [[250, 170, 450, 330]],
        ),
    )

    result = report.analyze(str(source))

    assert result["has_colour"] is True
    assert result["hue_label"] == "blue"
    assert "genuine coloured stone or enamel" in result["prompt_line"].lower()
    assert "blue" not in result["prompt_line"].lower()


def test_localisation_failure_never_asserts_a_colour(tmp_path, monkeypatch):
    source = tmp_path / "unknown.jpg"
    _synthetic_plate(source, blue_inside_product=False)
    monkeypatch.setattr(report, "_product_region_mask", lambda arr: (None, []))

    result = report.analyze(str(source))

    assert result["has_colour"] is None
    assert result["colour_measurement"] == "inconclusive_no_product_region"
    assert "blue" not in result["prompt_line"].lower()


def test_real_gr22_132_blue_counter_reflection_is_not_product_colour():
    source = (
        Path(__file__).parents[1]
        / "capture_intake"
        / "GENTS RING 22"
        / "GR22_132.jpg"
    )
    if not source.exists():
        pytest.skip("local regression capture is unavailable")

    result = report.analyze(str(source))

    assert result["has_colour"] is False
    assert "blue" not in result["prompt_line"].lower()
    assert result["localisation_boxes"] == [[1122, 433, 1410, 802]]


def test_real_multicolour_earring_retains_product_colours_without_guessing_hue():
    source = (
        Path(__file__).parents[1]
        / "processed"
        / "EARRING 22"
        / "ER22_92.jpg"
    )
    if not source.exists():
        pytest.skip("local multicolour regression capture is unavailable")

    result = report.analyze(str(source))

    assert result["has_colour"] is True
    assert "copy each visible product colour exactly" in result["prompt_line"].lower()
    # The coarse diagnostic median is cyan for combined green and magenta.
    # It must never become an instruction to invent cyan jewellery.
    assert "cyan" not in result["prompt_line"].lower()
