import json
from pathlib import Path

from PIL import Image

import codex_repair
import orn_item_image_sync
import review_queue


def _configure(monkeypatch, tmp_path: Path):
    paths = {
        "capture": tmp_path / "capture_intake",
        "processed": tmp_path / "processed",
        "output": tmp_path / "output",
        "rejected": tmp_path / "rejected",
        "needs": tmp_path / "needs_review",
        "input": tmp_path / "input",
        "data": tmp_path / "data",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(review_queue, "CAPTURE_INTAKE", str(paths["capture"]))
    monkeypatch.setattr(review_queue, "PROCESSED_DIR", str(paths["processed"]))
    monkeypatch.setattr(review_queue, "OUTPUT_DIR", str(paths["output"]))
    monkeypatch.setattr(review_queue, "REJECTED_DIR", str(paths["rejected"]))
    monkeypatch.setattr(review_queue, "NEEDS_REVIEW", str(paths["needs"]))
    monkeypatch.setattr(review_queue, "INPUT_DIR", str(paths["input"]))
    monkeypatch.setattr(review_queue, "STATE_PATH", str(paths["data"] / "review_state.json"))
    monkeypatch.setattr(review_queue, "FEEDBACK_PATH", str(paths["data"] / "feedback.jsonl"))
    monkeypatch.setattr(review_queue, "APPROVED_HASHES_PATH", str(paths["data"] / "approved_hashes.json"))
    monkeypatch.setattr(review_queue, "REJECTED_MANIFEST", str(paths["rejected"] / "REJECT_REASONS.txt"))
    monkeypatch.setattr(codex_repair, "AUDIT_PATH", paths["data"] / "codex_repair_imports.jsonl")
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
    return paths


def test_import_repair_publishes_then_approves_and_routes_raw(monkeypatch, tmp_path):
    paths = _configure(monkeypatch, tmp_path)
    raw = paths["capture"] / "BANGLE 22" / "BG22_7.jpg"
    failed = paths["rejected"] / "Bangle22" / "BG22_7.jpg"
    replacement = tmp_path / "replacement.png"
    raw.parent.mkdir()
    failed.parent.mkdir()
    raw.write_bytes(b"raw-master")
    failed.write_bytes(b"old-failed-delivery")
    Image.new("RGB", (500, 500), "white").save(replacement)
    Path(review_queue.STATE_PATH).write_text(
        json.dumps({"BG22_7": {"verdict": "rejected", "reason": "design_mismatch"}}),
        encoding="utf-8",
    )

    result = codex_repair.import_repair("BG22_7", replacement, note="restored design")

    assert result["review"]["verdict"] == "approved"
    assert (paths["output"] / "Bangle22" / "BG22_7.jpg").is_file()
    # The failed delivery is still preserved, but no longer as a second LIVE
    # image under the same label: since 2026-09-02 a superseded delivery is
    # archived to <category>/_superseded/, which the delivery walkers skip.
    # The audit record survives; the live set stays one-image-per-label.
    archived = list((failed.parent / review_queue.SUPERSEDED_DIRNAME).glob("BG22_7__*.jpg"))
    assert len(archived) == 1, "the failed delivery must be preserved, not destroyed"
    assert archived[0].read_bytes() == b"old-failed-delivery"
    assert not failed.exists(), "it must not remain a live delivery"
    assert not raw.exists()
    assert (paths["processed"] / "BANGLE 22" / "BG22_7.jpg").read_bytes() == b"raw-master"
    assert codex_repair.AUDIT_PATH.is_file()


def test_import_repair_refuses_non_rejected_label(monkeypatch, tmp_path):
    paths = _configure(monkeypatch, tmp_path)
    candidate = tmp_path / "replacement.png"
    Image.new("RGB", (20, 20), "white").save(candidate)
    Path(review_queue.STATE_PATH).write_text(
        json.dumps({"BG22_8": {"verdict": "approved"}}), encoding="utf-8"
    )

    try:
        codex_repair.import_repair("BG22_8", candidate, note="should fail")
    except ValueError as exc:
        assert "not currently rejected" in str(exc)
    else:
        raise AssertionError("approved label was accepted as a rejected repair")


def test_import_repair_infers_category_from_raw_when_delivery_is_missing(monkeypatch, tmp_path):
    paths = _configure(monkeypatch, tmp_path)
    raw = paths["capture"] / "JHUMKA 22" / "JB22_1.jpg"
    replacement = tmp_path / "replacement.png"
    raw.parent.mkdir()
    raw.write_bytes(b"raw-master")
    Image.new("RGB", (500, 500), "white").save(replacement)
    Path(review_queue.STATE_PATH).write_text(
        json.dumps({"JB22_1": {"verdict": "rejected", "reason": "design_mismatch"}}),
        encoding="utf-8",
    )

    codex_repair.import_repair("JB22_1", replacement, note="restored design")

    assert (paths["output"] / "Jhumka22" / "JB22_1.jpg").is_file()
    assert (paths["processed"] / "JHUMKA 22" / "JB22_1.jpg").is_file()
