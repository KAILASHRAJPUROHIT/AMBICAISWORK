from pathlib import Path

from PIL import Image

import app
import image_spec


def test_delivery_reduces_resolution_instead_of_discarding_api_result(
    tmp_path, monkeypatch
):
    raw = tmp_path / "azure.png"
    final = tmp_path / "final.jpg"
    raw.write_bytes(b"valid Azure result")
    attempted = []

    def fake_convert(source, output, **kwargs):
        edge = kwargs["target_size"][0]
        attempted.append(edge)
        if edge > 2800:
            raise ValueError(
                f"{edge}x{edge} JPEG cannot fit within 1000000 bytes "
                "at minimum quality 88"
            )
        # A real (if tiny) JPEG — _publish_delivery re-opens the converted
        # result for its own symmetry/colour-standardization pass, so the
        # mock has to produce something PIL can actually open, not literal
        # placeholder bytes.
        Image.new("RGB", (10, 10), (200, 150, 50)).save(output, "JPEG")

    monkeypatch.setattr(image_spec, "convert_delivery_image", fake_convert)
    result = app._publish_delivery(raw, final)

    assert attempted == [3200, 3000, 2800]
    assert final.is_file()
    with Image.open(final) as delivered:
        assert delivered.format == "JPEG"
    assert not raw.exists()
    assert result["resolution_adjusted"] is True
    assert result["final_edge"] == 2800
    assert result["maximum_file_bytes"] == 1_000_000
