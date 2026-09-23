import json

from PIL import Image
import pytest

import orn_item_image_sync as sync


def test_creates_exact_stock_category_folders(tmp_path):
    result = sync.create_stock_category_folders(
        server_root=tmp_path,
        stock_labels=("BG22/1", "GR22/1", "TP22/1"),
    )

    assert result["categories"] == 3
    assert (tmp_path / "BANGLE 22").is_dir()
    assert (tmp_path / "GENTS RING 22").is_dir()
    assert (tmp_path / "TOPS 22").is_dir()


def test_approved_image_uses_exact_ornate_nx_name_and_jpeg(tmp_path):
    source = tmp_path / "source.jpg"
    Image.new("RGB", (40, 30), (210, 170, 50)).save(source)
    manifest = tmp_path / "manifest.json"
    queue = tmp_path / "queue.json"
    sync.queue_upload("BG22_1", source, queue_path=queue)

    result = sync.publish_approved(
        "BG22_1",
        source,
        server_root=tmp_path / "server",
        stock_labels=("BG22/1",),
        manifest_path=manifest,
        queue_path=queue,
    )

    destination = tmp_path / "server" / "BANGLE 22" / "BG22_1.Jpg"
    assert result["destination"] == str(destination)
    assert destination.is_file()
    with Image.open(destination) as image:
        assert image.format == "JPEG"
        assert image.size == (40, 30)
    assert json.loads(queue.read_text(encoding="utf-8")) == {}


def test_non_stock_label_is_blocked(tmp_path):
    source = tmp_path / "source.jpg"
    Image.new("RGB", (10, 10)).save(source)

    with pytest.raises(ValueError, match="expected one current-stock label"):
        sync.publish_approved(
            "NOT_STOCK_1",
            source,
            server_root=tmp_path / "server",
            stock_labels=("BG22/1",),
            manifest_path=tmp_path / "manifest.json",
        )
