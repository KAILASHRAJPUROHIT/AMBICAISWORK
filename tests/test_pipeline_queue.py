"""Safety and lifecycle tests for the additive processing queue."""

import hashlib
import os
import sys
from pathlib import Path

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pipeline_queue as queue
import capture_voids


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _roots(tmp_path):
    return {
        "source_root": tmp_path / "capture_intake",
        "master_root": tmp_path / "capture",
        "processing_root": tmp_path / "processing",
        "processed_root": tmp_path / "processed",
        "needs_review_root": tmp_path / "needs_review",
        "rejected_root": tmp_path / "rejected",
        "void_registry_path": tmp_path / "capture_voids.json",
    }


def _write_capture(root, relative, content, timestamp_ns):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, ns=(timestamp_ns, timestamp_ns))
    return path


def _sync(roots, *, now_ns=20_000_000_000):
    return queue.sync_intake_once(
        **roots,
        stable_age_seconds=1,
        now_ns=now_ns,
    )


def test_sync_preserves_master_and_queues_only_primary_images(tmp_path):
    roots = _roots(tmp_path)
    source = roots["source_root"]
    old = _write_capture(
        source,
        Path("Ladies Rings 1") / "LR22_1.jpg",
        b"old jewel",
        1_000_000_000,
    )
    newer = _write_capture(
        source,
        Path("Earrings 1") / "ER22_1.jpg",
        b"new jewel",
        2_000_000_000,
    )
    archived = _write_capture(
        source,
        Path("Ladies Rings 1") / "_tag_archive" / "LR22_1_tag.jpg",
        b"tag audit",
        1_000_000_000,
    )
    before = {
        path: (path.stat().st_mtime_ns, _hash(path))
        for path in (old, newer, archived)
    }

    result = _sync(roots)

    assert result.queued == (
        Path("Ladies Rings 1/LR22_1.jpg"),
        Path("Earrings 1/ER22_1.jpg"),
    )
    assert result.ignored_for_processing == (
        Path("Ladies Rings 1/_tag_archive/LR22_1_tag.jpg"),
    )
    assert (
        roots["master_root"]
        / "Ladies Rings 1"
        / "_tag_archive"
        / "LR22_1_tag.jpg"
    ).read_bytes() == b"tag audit"
    assert not (
        roots["processing_root"]
        / "Ladies Rings 1"
        / "_tag_archive"
        / "LR22_1_tag.jpg"
    ).exists()
    assert {
        path: (path.stat().st_mtime_ns, _hash(path))
        for path in (old, newer, archived)
    } == before


def test_practice_folder_is_mirrored_but_never_queued(tmp_path):
    roots = _roots(tmp_path)
    practice = _write_capture(
        roots["source_root"],
        Path("_TEST") / "TEST_1.jpg",
        b"practice only",
        1_000_000_000,
    )

    result = _sync(roots)

    relative = Path("_TEST/TEST_1.jpg")
    assert result.mirrored == (relative,)
    assert result.ignored_for_processing == (relative,)
    assert (roots["master_root"] / relative).read_bytes() == b"practice only"
    assert not (roots["processing_root"] / relative).exists()
    assert practice.read_bytes() == b"practice only"


def test_voided_pair_is_mirrored_but_primary_is_never_queued(tmp_path):
    roots = _roots(tmp_path)
    relative = Path("Pendant 1/PD22_1.jpg")
    tag_relative = Path("Pendant 1/_tag_archive/PD22_1_tag.jpg")
    primary = _write_capture(
        roots["source_root"], relative, b"voided jewel", 1_000_000_000
    )
    tag = _write_capture(
        roots["source_root"], tag_relative, b"audit tag", 1_000_000_000
    )
    capture_voids.record_void(
        primary_path=relative,
        tag_path=tag_relative,
        tag_code="PD22/1",
        category="pendant",
        folder="Pendant 1",
        primary_size=primary.stat().st_size,
        tag_size=tag.stat().st_size,
        registry_path=roots["void_registry_path"],
        voided_at=10.0,
    )

    result = _sync(roots)

    assert result.queued == ()
    assert result.voided_for_processing == (relative,)
    assert result.voided_moved_to_rejected == ()
    assert (roots["master_root"] / relative).read_bytes() == b"voided jewel"
    assert (roots["master_root"] / tag_relative).read_bytes() == b"audit tag"
    assert not (roots["processing_root"] / relative).exists()
    assert primary.read_bytes() == b"voided jewel"
    assert tag.read_bytes() == b"audit tag"


def test_already_queued_void_is_atomically_moved_to_rejected(tmp_path):
    roots = _roots(tmp_path)
    relative = Path("Locket 1/LC22_1.jpg")
    tag_relative = Path("Locket 1/_tag_archive/LC22_1_tag.jpg")
    primary = _write_capture(
        roots["source_root"], relative, b"wrong jewel", 1_000_000_000
    )
    tag = _write_capture(
        roots["source_root"], tag_relative, b"wrong tag", 1_000_000_000
    )
    queued = _write_capture(
        roots["processing_root"], relative, b"wrong jewel", 1_000_000_000
    )
    capture_voids.record_void(
        primary_path=relative,
        tag_path=tag_relative,
        tag_code="LC22/1",
        category="locket",
        folder="Locket 1",
        primary_size=primary.stat().st_size,
        tag_size=tag.stat().st_size,
        registry_path=roots["void_registry_path"],
        voided_at=10.0,
    )

    result = _sync(roots)

    assert result.voided_moved_to_rejected == (relative,)
    assert not queued.exists()
    assert (roots["rejected_root"] / relative).read_bytes() == b"wrong jewel"
    assert primary.read_bytes() == b"wrong jewel"
    assert tag.read_bytes() == b"wrong tag"


def test_corrupt_void_registry_fails_closed_before_any_item_is_queued(tmp_path):
    roots = _roots(tmp_path)
    relative = Path("Tops 1/TP22_9.jpg")
    source = _write_capture(
        roots["source_root"], relative, b"status unknown", 1_000_000_000
    )
    roots["void_registry_path"].write_text("{broken", encoding="utf-8")

    with pytest.raises(capture_voids.VoidRegistryError, match="unreadable"):
        _sync(roots)

    assert source.read_bytes() == b"status unknown"
    assert not (roots["master_root"] / relative).exists()
    assert not (roots["processing_root"] / relative).exists()


def test_sync_is_idempotent(tmp_path):
    roots = _roots(tmp_path)
    _write_capture(
        roots["source_root"],
        Path("Tops 1") / "TP22_1.jpg",
        b"jewel",
        1_000_000_000,
    )

    first = _sync(roots)
    second = _sync(roots)

    assert first.queued == (Path("Tops 1/TP22_1.jpg"),)
    assert second.mirrored == ()
    assert second.queued == ()
    assert second.already_mirrored == (Path("Tops 1/TP22_1.jpg"),)
    assert second.already_queued == (Path("Tops 1/TP22_1.jpg"),)


def test_recent_files_are_not_mirrored_or_queued(tmp_path):
    roots = _roots(tmp_path)
    recent = _write_capture(
        roots["source_root"],
        Path("Tops 1") / "TP22_1.jpg",
        b"still writing",
        19_500_000_000,
    )

    result = _sync(roots)

    assert result.skipped_recent == (Path("Tops 1/TP22_1.jpg"),)
    assert not roots["master_root"].joinpath("Tops 1", "TP22_1.jpg").exists()
    assert recent.read_bytes() == b"still writing"


def test_different_existing_destination_fails_without_overwrite(tmp_path):
    roots = _roots(tmp_path)
    _write_capture(
        roots["source_root"],
        Path("Tops 1") / "TP22_1.jpg",
        b"source jewel",
        1_000_000_000,
    )
    conflicting = _write_capture(
        roots["master_root"],
        Path("Tops 1") / "TP22_1.jpg",
        b"different bytes",
        1_000_000_000,
    )

    with pytest.raises(queue.FileConflictError):
        _sync(roots)

    assert conflicting.read_bytes() == b"different bytes"


def test_terminal_item_is_not_silently_requeued(tmp_path):
    roots = _roots(tmp_path)
    relative = Path("Tops 1") / "TP22_1.jpg"
    _write_capture(
        roots["source_root"],
        relative,
        b"jewel",
        1_000_000_000,
    )
    _write_capture(
        roots["processed_root"],
        relative,
        b"jewel",
        1_000_000_000,
    )

    result = _sync(roots)

    assert result.queued == ()
    assert result.already_handled == (relative,)
    assert not (roots["processing_root"] / relative).exists()


@pytest.mark.parametrize(
    ("transition", "target_name"),
    [
        (queue.mark_processed, "processed_root"),
        (queue.mark_needs_review, "needs_review_root"),
        (queue.mark_rejected, "rejected_root"),
    ],
)
def test_lifecycle_transition(tmp_path, transition, target_name):
    roots = _roots(tmp_path)
    relative = Path("Gents Rings 1") / "GR22_1.jpg"
    source = _write_capture(
        roots["processing_root"],
        relative,
        b"queued jewel",
        1_000_000_000,
    )

    keyword = {
        "processing_root": roots["processing_root"],
        target_name: roots[target_name],
    }
    destination = transition(relative, **keyword)

    assert destination.read_bytes() == b"queued jewel"
    assert not source.exists()


@pytest.mark.parametrize(
    ("status", "target_name"),
    [
        ("needs_review", "needs_review_root"),
        ("rejected", "rejected_root"),
    ],
)
def test_review_and_rejected_items_can_be_requeued(tmp_path, status, target_name):
    roots = _roots(tmp_path)
    relative = Path("Gents Rings 1") / "GR22_1.jpg"
    destination = _write_capture(
        roots[target_name],
        relative,
        b"held jewel",
        1_000_000_000,
    )

    requeued = queue.requeue_item(
        relative,
        status=status,
        processing_root=roots["processing_root"],
        needs_review_root=roots["needs_review_root"],
        rejected_root=roots["rejected_root"],
    )
    assert requeued.read_bytes() == b"held jewel"
    assert not destination.exists()


def test_lifecycle_transition_refuses_overwrite(tmp_path):
    roots = _roots(tmp_path)
    relative = Path("Tops 1") / "TP22_1.jpg"
    source = _write_capture(
        roots["processing_root"],
        relative,
        b"queued jewel",
        1_000_000_000,
    )
    destination = _write_capture(
        roots["processed_root"],
        relative,
        b"existing processed jewel",
        1_000_000_000,
    )

    with pytest.raises(queue.FileConflictError):
        queue.mark_processed(
            relative,
            processing_root=roots["processing_root"],
            processed_root=roots["processed_root"],
        )

    assert source.read_bytes() == b"queued jewel"
    assert destination.read_bytes() == b"existing processed jewel"


def test_lifecycle_transition_rejects_path_traversal(tmp_path):
    roots = _roots(tmp_path)

    with pytest.raises(ValueError, match="Unsafe"):
        queue.mark_rejected(
            Path("..") / "capture_intake" / "do-not-touch.jpg",
            processing_root=roots["processing_root"],
            rejected_root=roots["rejected_root"],
        )


def test_requeue_rejects_any_status_other_than_review_or_rejected(tmp_path):
    roots = _roots(tmp_path)

    with pytest.raises(ValueError, match="needs_review.*rejected"):
        queue.requeue_item(
            Path("Tops 1") / "TP22_1.jpg",
            status="capture",
            processing_root=roots["processing_root"],
            needs_review_root=roots["needs_review_root"],
            rejected_root=roots["rejected_root"],
        )
