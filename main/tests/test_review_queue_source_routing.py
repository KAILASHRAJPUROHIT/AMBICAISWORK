import json
from pathlib import Path

import review_queue
import orn_item_image_sync


def _isolate_review_queue(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    roots = {
        "capture": tmp_path / "capture_intake",
        "processed": tmp_path / "processed",
        "output": tmp_path / "output",
        "rejected": tmp_path / "rejected",
        "needs_review": tmp_path / "needs_review",
        "input": tmp_path / "input",
        "data": tmp_path / "data",
        "reports": tmp_path / "reports",
    }
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(review_queue, "CAPTURE_INTAKE", str(roots["capture"]))
    monkeypatch.setattr(review_queue, "PROCESSED_DIR", str(roots["processed"]))
    monkeypatch.setattr(review_queue, "OUTPUT_DIR", str(roots["output"]))
    monkeypatch.setattr(review_queue, "REJECTED_DIR", str(roots["rejected"]))
    monkeypatch.setattr(review_queue, "NEEDS_REVIEW", str(roots["needs_review"]))
    monkeypatch.setattr(review_queue, "INPUT_DIR", str(roots["input"]))
    monkeypatch.setattr(review_queue, "STATE_PATH", str(roots["data"] / "review_state.json"))
    monkeypatch.setattr(review_queue, "FEEDBACK_PATH", str(roots["data"] / "feedback.jsonl"))
    monkeypatch.setattr(review_queue, "APPROVED_HASHES_PATH", str(roots["data"] / "approved_hashes.json"))
    monkeypatch.setattr(review_queue, "REJECTED_MANIFEST", str(roots["rejected"] / "REJECT_REASONS.txt"))
    monkeypatch.setattr(review_queue, "DEDUP_HASH_CACHE_PATH", str(roots["data"] / "dedup_hash_cache.json"))
    monkeypatch.setattr(review_queue, "DEDUP_REPORT_PATH", str(roots["reports"] / "dedup_check" / "latest.json"))
    monkeypatch.setattr(
        orn_item_image_sync,
        "publish_approved",
        lambda label, source: {"ok": True, "label": label, "source": source},
    )
    monkeypatch.setattr(
        orn_item_image_sync,
        "record_failure",
        lambda label, error: {"ok": False, "label": label},
    )
    monkeypatch.setattr(
        orn_item_image_sync,
        "queue_upload",
        lambda label, source, error: {"ok": False, "queued": True, "label": label},
    )
    monkeypatch.setattr(orn_item_image_sync, "trigger_user_upload_worker", lambda: None)
    return roots


def test_approval_moves_raw_master_from_capture_to_processed(monkeypatch, tmp_path):
    roots = _isolate_review_queue(monkeypatch, tmp_path)
    source = roots["capture"] / "BANGLE 22" / "BG22_1.jpg"
    delivery = roots["output"] / "Bangle22" / "BG22_1.jpg"
    source.parent.mkdir()
    delivery.parent.mkdir()
    source.write_bytes(b"raw-master")
    delivery.write_bytes(b"delivery")

    review_queue.set_verdict("BG22_1", review_queue.APPROVED)

    assert not source.exists()
    assert (roots["processed"] / "BANGLE 22" / "BG22_1.jpg").read_bytes() == b"raw-master"
    state = json.loads((roots["data"] / "review_state.json").read_text(encoding="utf-8"))
    assert state["BG22_1"]["verdict"] == review_queue.APPROVED


def test_approval_removes_only_byte_identical_capture_duplicate(monkeypatch, tmp_path):
    roots = _isolate_review_queue(monkeypatch, tmp_path)
    capture = roots["capture"] / "BANGLE 22" / "BG22_2.jpg"
    processed = roots["processed"] / "BANGLE 22" / "BG22_2.jpg"
    capture.parent.mkdir()
    processed.parent.mkdir()
    capture.write_bytes(b"same-raw-master")
    processed.write_bytes(b"same-raw-master")

    review_queue.set_verdict("BG22_2", review_queue.APPROVED)

    assert not capture.exists()
    assert processed.read_bytes() == b"same-raw-master"


def test_approval_preserves_conflicting_raws_for_manual_resolution(monkeypatch, tmp_path):
    roots = _isolate_review_queue(monkeypatch, tmp_path)
    capture = roots["capture"] / "BANGLE 22" / "BG22_3.jpg"
    processed = roots["processed"] / "BANGLE 22" / "BG22_3.jpg"
    capture.parent.mkdir()
    processed.parent.mkdir()
    capture.write_bytes(b"capture-version")
    processed.write_bytes(b"different-processed-version")

    review_queue.set_verdict("BG22_3", review_queue.APPROVED)

    assert capture.read_bytes() == b"capture-version"
    assert processed.read_bytes() == b"different-processed-version"
    report = review_queue.check_capture_rejected_dedup()
    assert "BG22_3" in report["label_conflicts"]


def test_startup_reconciliation_routes_approved_and_rejected_raws(monkeypatch, tmp_path):
    roots = _isolate_review_queue(monkeypatch, tmp_path)
    approved_capture = roots["capture"] / "BANGLE 22" / "BG22_4.jpg"
    approved_processed = roots["processed"] / "BANGLE 22" / "BG22_4.jpg"
    rejected_capture = roots["capture"] / "BANGLE 22" / "BG22_5.jpg"
    rejected_processed = roots["processed"] / "BANGLE 22" / "BG22_5.jpg"
    approved_capture.parent.mkdir()
    approved_processed.parent.mkdir()
    for path in (approved_capture, approved_processed):
        path.write_bytes(b"approved-raw")
    for path in (rejected_capture, rejected_processed):
        path.write_bytes(b"rejected-raw")
    (roots["data"] / "review_state.json").write_text(
        json.dumps({
            "BG22_4": {"verdict": review_queue.APPROVED},
            "BG22_5": {"verdict": review_queue.REJECTED},
        }),
        encoding="utf-8",
    )

    result = review_queue.reconcile_source_routes()

    assert result["repaired"] == 2
    assert not approved_capture.exists()
    assert approved_processed.read_bytes() == b"approved-raw"
    assert rejected_capture.read_bytes() == b"rejected-raw"
    assert not rejected_processed.exists()
    assert result["conflicts"] == []


def test_rejection_moves_every_delivery_variant_out_of_output(monkeypatch, tmp_path):
    roots = _isolate_review_queue(monkeypatch, tmp_path)
    raw = roots["capture"] / "GENTS RING 22" / "GR22_9.jpg"
    first = roots["output"] / "GentsRing22" / "GR22_9.jpg"
    retry = roots["output"] / "GentsRing22" / "GR22_9_2.jpg"
    raw.parent.mkdir()
    first.parent.mkdir()
    raw.write_bytes(b"raw-master")
    first.write_bytes(b"first-delivery")
    retry.write_bytes(b"different-retry-delivery")

    review_queue.set_verdict("GR22_9", review_queue.REJECTED, "design_mismatch")

    assert not first.exists()
    assert not retry.exists()
    assert (roots["rejected"] / "GentsRing22" / "GR22_9.jpg").read_bytes() == b"first-delivery"
    assert (roots["rejected"] / "GentsRing22" / "GR22_9_2.jpg").read_bytes() == b"different-retry-delivery"
    assert raw.exists()


def test_approval_publishes_delivery_but_rejection_does_not(monkeypatch, tmp_path):
    roots = _isolate_review_queue(monkeypatch, tmp_path)
    approved_delivery = roots["output"] / "Bangle22" / "BG22_10.jpg"
    rejected_delivery = roots["output"] / "Bangle22" / "BG22_11.jpg"
    approved_delivery.parent.mkdir()
    approved_delivery.write_bytes(b"approved-delivery")
    rejected_delivery.write_bytes(b"rejected-delivery")
    calls = []

    def fake_publish(label, source):
        calls.append((label, source))
        return {"ok": True, "label": label}

    monkeypatch.setattr(orn_item_image_sync, "publish_approved", fake_publish)
    review_queue.set_verdict("BG22_10", review_queue.APPROVED)
    review_queue.set_verdict("BG22_11", review_queue.REJECTED, "design_mismatch")

    assert calls == [("BG22_10", str(approved_delivery))]
