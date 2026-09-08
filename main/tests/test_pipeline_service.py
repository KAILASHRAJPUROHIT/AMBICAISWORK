"""Read-only preview and explicit coordinator tests."""

import os
import sys
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pipeline_service


def _coordinator(tmp_path):
    return pipeline_service.PipelineCoordinator(
        source_capture_root=tmp_path / "capture_intake",
        master_capture_root=tmp_path / "capture",
        processing_root=tmp_path / "processing",
        processed_root=tmp_path / "processed",
        needs_review_root=tmp_path / "needs_review",
        rejected_root=tmp_path / "rejected",
        void_registry_path=tmp_path / "capture_voids.json",
        stock_dir=tmp_path / "Stock",
    )


def _write(root, relative, content=b"image", mtime_ns=1_000_000_000):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def test_construction_and_preview_do_not_create_target_roots(tmp_path):
    service = _coordinator(tmp_path)
    source = service.source_capture_root
    _write(source, Path("Tops 1") / "TP22_1.jpg")
    _write(source, Path("Tops 1") / "_tag_archive" / "TP22_1_tag.jpg")

    preview = service.preview(
        stable_age_seconds=1,
        now_ns=20_000_000_000,
    )

    assert preview.source_files == 2
    assert preview.stable_primary_images == 1
    assert preview.stable_tag_archives == 1
    assert preview.files_to_mirror == 2
    assert preview.items_to_queue == 1
    assert preview.safe_to_activate is True
    assert not service.master_capture_root.exists()
    assert not service.processing_root.exists()


def test_preview_detects_foreign_processing_files(tmp_path):
    service = _coordinator(tmp_path)
    _write(
        service.source_capture_root,
        Path("Tops 1") / "TP22_1.jpg",
    )
    _write(
        service.processing_root,
        Path("legacy") / "camera-file.jpg",
    )

    preview = service.preview(
        stable_age_seconds=1,
        now_ns=20_000_000_000,
    )

    assert preview.foreign_processing_files == (
        Path("legacy/camera-file.jpg"),
    )
    assert preview.safe_to_activate is False


def test_explicit_sync_then_preview_is_idempotent(tmp_path):
    service = _coordinator(tmp_path)
    relative = Path("Tops 1") / "TP22_1.jpg"
    _write(service.source_capture_root, relative)

    result = service.sync_intake()
    preview = service.preview(stable_age_seconds=0)

    assert result.queued == (relative,)
    assert preview.items_to_queue == 0
    assert preview.already_queued == 1
    assert service.last_sync_error is None
    assert service.last_sync_at is not None


def test_dashboard_counts_live_capture_intake_not_archival_mirror(tmp_path):
    service = _coordinator(tmp_path)
    _write(service.source_capture_root, Path("1 TOPS 22") / "TP22_1.jpg")
    _write(service.master_capture_root, Path("legacy") / "stale-a.jpg")
    _write(service.master_capture_root, Path("legacy") / "stale-b.jpg")

    stats = service.dashboard()

    assert stats.captured_total == 1


def test_dashboard_uses_current_inventory_count_when_routing_snapshot_is_older(
    tmp_path, monkeypatch
):
    service = _coordinator(tmp_path)
    monkeypatch.setattr(
        type(service.stock), "inventory_tag_count", property(lambda _self: 2814)
    )

    stats = service.dashboard()

    assert stats.stock_tags == 2814
