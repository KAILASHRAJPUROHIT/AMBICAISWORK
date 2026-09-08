from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

import app
import image_spec
import item_routing


def _raw_image(path: Path) -> None:
    Image.new("RGB", (320, 200), (90, 40, 10)).save(path, "JPEG")


def test_generated_studio_moves_to_variety_folder(tmp_path, monkeypatch):
    raw = tmp_path / "engine-output.jpg"
    _raw_image(raw)
    target = tmp_path / "output" / "FANCY" / "LC22_13.jpg"
    model = tmp_path / "output" / "FANCY" / "LC22_13_2.jpg"
    resolved = item_routing.VarietyOutputPaths(
        variety="FANCY",
        output_bucket="FANCY",
        studio_output=target,
        model_output=model,
    )
    monkeypatch.setattr(app, "_resolve_variety_output", lambda label, category: resolved)

    output_path, output_dir, paths = app._move_generated_to_variety_output(
        str(raw), "LC22_13", "LC22_13", "lockets"
    )

    assert not raw.exists()
    with Image.open(target) as image:
        assert image.size == (2400, 2400)
        assert image.info.get("icc_profile")
        assert image.info.get("xmp")
    assert target.stat().st_size <= 1_000_000
    assert output_path == str(target)
    assert output_dir == str(target.parent)
    assert paths.output_bucket == "FANCY"


def test_real_safe_capture_label_resolves_stock_variety():
    app._PIPELINE_COORDINATOR = None

    paths = app._resolve_variety_output("LC22_13", "lockets")

    assert paths.variety == "FANCY"
    assert paths.output_bucket == "FANCY"
    assert paths.studio_output.name == "LC22_13.jpg"
    assert paths.model_output.name == "LC22_13_2.jpg"


def test_unknown_stock_label_is_not_silently_general():
    app._PIPELINE_COORDINATOR = None

    try:
        app._resolve_variety_output("NOT_A_REAL_TAG", "lockets")
    except item_routing.RoutingError as exc:
        assert "not present" in str(exc)
    else:
        raise AssertionError("unknown stock label was routed to GENERAL")


def test_unrouted_generated_image_is_preserved_for_review(tmp_path, monkeypatch):
    import paths

    raw = tmp_path / "engine-output.jpg"
    _raw_image(raw)
    review_root = tmp_path / "needs_review"
    monkeypatch.setattr(paths, "NEEDS_REVIEW_DIR", str(review_root))

    destination = app._preserve_unrouted_output(str(raw), "UNKNOWN")

    assert not raw.exists()
    with Image.open(destination) as image:
        assert image.size == (2400, 2400)
        assert image.info.get("icc_profile")
        assert image.info.get("xmp")
    assert Path(destination).stat().st_size <= 1_000_000
    assert Path(destination).parent == review_root / "stock_unmatched"


def test_failed_size_cap_never_replaces_existing_delivery(tmp_path, monkeypatch):
    raw = tmp_path / "engine-output.jpg"
    destination = tmp_path / "output" / "GENERAL" / "ER22_1.jpg"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"existing-good-delivery")
    _raw_image(raw)
    monkeypatch.setattr(image_spec, "MAX_FILE_BYTES", 10)

    with pytest.raises(ValueError, match="cannot fit"):
        app._publish_capped_delivery(str(raw), str(destination))

    assert destination.read_bytes() == b"existing-good-delivery"
    assert raw.exists()
