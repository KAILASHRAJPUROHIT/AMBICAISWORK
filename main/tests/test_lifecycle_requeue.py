from __future__ import annotations

import os
from pathlib import Path

import pytest

import app
import lifecycle_requeue


def _service(tmp_path):
    return lifecycle_requeue.LifecycleRequeueService(
        processing_root=tmp_path / "processing",
        needs_review_root=tmp_path / "needs_review",
        rejected_root=tmp_path / "rejected",
    )


def _write(root: Path, relative: str, content=b"image") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _client(monkeypatch, service):
    monkeypatch.setattr(app, "_get_lifecycle_requeue_service", lambda: service)
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["authed"] = True
    return client


@pytest.mark.parametrize("status", ["needs_review", "rejected"])
def test_list_and_preview_are_read_only(tmp_path, status):
    service = _service(tmp_path)
    source = _write(service.status_roots[status], "Earrings 1/ER22_1.jpg")
    before = source.stat()

    items = service.list_items(status)
    preview = service.preview(status, "Earrings 1/ER22_1.jpg")

    assert [item.relative_path for item in items] == ["Earrings 1/ER22_1.jpg"]
    assert preview["can_requeue"] is True
    assert preview["confirmation_token"].startswith(f"REQUEUE::{status}::")
    assert source.read_bytes() == b"image"
    assert source.stat().st_mtime_ns == before.st_mtime_ns
    assert not service.processing_root.exists()


def test_list_missing_root_is_empty_and_does_not_create_it(tmp_path):
    service = _service(tmp_path)

    assert service.list_items("needs_review") == ()
    assert not service.status_roots["needs_review"].exists()


def test_confirmed_requeue_moves_atomically_and_returns_metadata(tmp_path):
    service = _service(tmp_path)
    source = _write(service.status_roots["rejected"], "Locket 2/LC22_2.jpg", b"held")
    preview = service.preview("rejected", "Locket 2/LC22_2.jpg")

    result = service.requeue(
        "rejected",
        "Locket 2/LC22_2.jpg",
        preview["confirmation_token"],
    )

    destination = service.processing_root / "Locket 2/LC22_2.jpg"
    assert result["ok"] is True
    assert result["destination"]["relative_path"] == "Locket 2/LC22_2.jpg"
    assert result["destination"]["size"] == 4
    assert destination.read_bytes() == b"held"
    assert not source.exists()


def test_stale_or_wrong_confirmation_is_rejected_without_move(tmp_path):
    service = _service(tmp_path)
    source = _write(service.status_roots["needs_review"], "Tops 1/TP22_1.jpg")
    preview = service.preview("needs_review", "Tops 1/TP22_1.jpg")
    source.write_bytes(b"changed after preview")

    with pytest.raises(lifecycle_requeue.RequeueValidationError, match="exactly"):
        service.requeue(
            "needs_review",
            "Tops 1/TP22_1.jpg",
            preview["confirmation_token"],
        )
    assert source.exists()
    assert not (service.processing_root / "Tops 1/TP22_1.jpg").exists()


def test_existing_processing_destination_is_conflict_without_overwrite(tmp_path):
    service = _service(tmp_path)
    source = _write(service.status_roots["rejected"], "Tops 1/TP22_1.jpg", b"held")
    destination = _write(service.processing_root, "Tops 1/TP22_1.jpg", b"queued")
    preview = service.preview("rejected", "Tops 1/TP22_1.jpg")

    assert preview["can_requeue"] is False
    with pytest.raises(lifecycle_requeue.RequeueConflictError):
        service.requeue(
            "rejected", "Tops 1/TP22_1.jpg", preview["confirmation_token"]
        )
    assert source.read_bytes() == b"held"
    assert destination.read_bytes() == b"queued"


@pytest.mark.parametrize(
    ("status", "path"),
    [
        ("capture", "Tops 1/TP22_1.jpg"),
        ("needs_review", "../capture/TP22_1.jpg"),
        ("rejected", "C:/outside.jpg"),
        ("rejected", ""),
    ],
)
def test_invalid_status_or_path_is_rejected(tmp_path, status, path):
    with pytest.raises(lifecycle_requeue.RequeueValidationError):
        _service(tmp_path).preview(status, path)


def test_symlink_escape_is_rejected_when_supported(tmp_path):
    service = _service(tmp_path)
    outside = _write(tmp_path / "outside", "escape.jpg")
    held = service.status_roots["rejected"]
    held.mkdir(parents=True)
    link = held / "link.jpg"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    with pytest.raises(lifecycle_requeue.RequeueValidationError, match="escapes"):
        service.preview("rejected", "link.jpg")


def test_api_contract_and_http_statuses(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _write(service.status_roots["needs_review"], "Earrings 1/ER22_1.jpg")
    client = _client(monkeypatch, service)

    listing = client.get("/api/pipeline/requeue?status=needs_review")
    assert listing.status_code == 200
    assert listing.get_json()["items"][0]["relative_path"] == "Earrings 1/ER22_1.jpg"

    preview = client.get(
        "/api/pipeline/requeue/preview",
        query_string={"status": "needs_review", "path": "Earrings 1/ER22_1.jpg"},
    )
    token = preview.get_json()["confirmation_token"]
    moved = client.post(
        "/api/pipeline/requeue",
        json={
            "status": "needs_review",
            "path": "Earrings 1/ER22_1.jpg",
            "confirmation_token": token,
        },
    )
    assert moved.status_code == 200
    assert moved.get_json()["destination"]["status"] == "processing"

    missing = client.get(
        "/api/pipeline/requeue/preview",
        query_string={"status": "rejected", "path": "missing.jpg"},
    )
    invalid = client.get("/api/pipeline/requeue?status=processed")
    assert missing.status_code == 404
    assert invalid.status_code == 400


def test_api_conflict_is_409_and_bad_confirmation_is_400(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _write(service.status_roots["rejected"], "Pendant 1/PD22_1.jpg", b"held")
    _write(service.processing_root, "Pendant 1/PD22_1.jpg", b"queued")
    client = _client(monkeypatch, service)
    preview = client.get(
        "/api/pipeline/requeue/preview",
        query_string={"status": "rejected", "path": "Pendant 1/PD22_1.jpg"},
    ).get_json()

    bad = client.post(
        "/api/pipeline/requeue",
        json={"status": "rejected", "path": "Pendant 1/PD22_1.jpg", "confirmation_token": "yes"},
    )
    conflict = client.post(
        "/api/pipeline/requeue",
        json={
            "status": "rejected",
            "path": "Pendant 1/PD22_1.jpg",
            "confirmation_token": preview["confirmation_token"],
        },
    )
    assert bad.status_code == 400
    assert conflict.status_code == 409
