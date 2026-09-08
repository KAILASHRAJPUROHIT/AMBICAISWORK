from pathlib import Path

import pytest
from PIL import Image

import image_spec


def _landscape_source(path: Path) -> bytes:
    image = Image.new("RGB", (300, 200), "green")
    for x in range(50):
        for y in range(200):
            image.putpixel((x, y), (255, 0, 0))
            image.putpixel((299 - x, y), (0, 0, 255))
    image.save(path, "PNG")
    image.close()
    return path.read_bytes()


@pytest.mark.parametrize("strategy", ["crop", "pad"])
def test_both_strategies_publish_exact_delivery_metadata(
    tmp_path, strategy
):
    source = tmp_path / "source.png"
    original = _landscape_source(source)
    output = tmp_path / f"{strategy}.jpg"

    result = image_spec.convert_delivery_image(
        source, output, strategy=strategy
    )

    assert source.read_bytes() == original
    assert (result.width, result.height) == (2400, 2400)
    assert result.mode == "RGB"
    assert result.has_icc_profile is True
    assert result.has_ai_source_metadata is True
    assert result.dpi == pytest.approx((72, 72), abs=0.1)
    assert result.file_bytes == output.stat().st_size


def test_crop_removes_long_edges_while_pad_preserves_them(tmp_path):
    source = tmp_path / "source.png"
    _landscape_source(source)
    crop = tmp_path / "crop.jpg"
    pad = tmp_path / "pad.jpg"

    image_spec.convert_delivery_image(source, crop, strategy="crop")
    image_spec.convert_delivery_image(source, pad, strategy="pad")

    with Image.open(crop) as cropped, Image.open(pad) as padded:
        crop_left = cropped.getpixel((30, 1200))
        crop_right = cropped.getpixel((2370, 1200))
        pad_left = padded.getpixel((30, 1200))
        pad_right = padded.getpixel((2370, 1200))
        assert crop_left[1] > crop_left[0]
        assert crop_right[1] > crop_right[2]
        assert pad_left[0] > pad_left[1]
        assert pad_right[2] > pad_right[1]


def test_conversion_never_overwrites_without_explicit_permission(tmp_path):
    source = tmp_path / "source.png"
    _landscape_source(source)
    output = tmp_path / "existing.jpg"
    output.write_bytes(b"keep")

    with pytest.raises(FileExistsError):
        image_spec.convert_delivery_image(source, output, strategy="crop")

    assert output.read_bytes() == b"keep"


def test_strategy_must_be_explicit_and_valid(tmp_path):
    source = tmp_path / "source.png"
    _landscape_source(source)

    with pytest.raises(ValueError, match="strategy"):
        image_spec.convert_delivery_image(
            source, tmp_path / "bad.jpg", strategy="stretch"
        )


def test_source_and_output_cannot_be_same_file(tmp_path):
    source = tmp_path / "source.png"
    _landscape_source(source)

    with pytest.raises(ValueError, match="different"):
        image_spec.convert_delivery_image(
            source, source, strategy="pad", overwrite=True
        )


def test_high_entropy_image_never_crosses_one_million_bytes(tmp_path):
    source = tmp_path / "noise.png"
    output = tmp_path / "noise.jpg"
    noise = Image.effect_noise((2400, 2400), 100).convert("RGB")
    noise.save(source, "PNG")
    noise.close()

    result = image_spec.convert_delivery_image(
        source, output, strategy="crop"
    )

    assert result.file_bytes <= 1_000_000
    assert output.stat().st_size <= 1_000_000
    with Image.open(output) as image:
        assert image.size == (2400, 2400)
        assert image.info.get("icc_profile")
        assert image.info.get("xmp")


def test_tablet_master_supports_larger_sharpened_delivery(tmp_path):
    source = tmp_path / "source.png"
    _landscape_source(source)
    output = tmp_path / "tablet.jpg"

    result = image_spec.convert_delivery_image(
        source,
        output,
        strategy="pad",
        target_size=(3200, 3200),
        sharpen=True,
        maximum_file_bytes=2_000_000,
    )

    assert (result.width, result.height) == (3200, 3200)
    assert result.file_bytes <= 2_000_000
    assert result.has_icc_profile is True
    assert result.has_ai_source_metadata is True
