import os
import shutil
import asyncio
import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.database import SessionLocal, Base, engine
from backend.models import Bill, AuditLog, Payment
from backend.invoice_lifecycle import (
    DUPLICATE_QUARANTINE_COPY,
    DUPLICATE_MOVE_FAILED_PERMISSION,
    DUPLICATE_PERMISSION_OPERATOR_MESSAGE,
    DUPLICATE_PERMISSION_MESSAGE,
    PDF_RETENTION_DAYS,
    assert_can_delete_pdf,
    handle_duplicate,
    run_archive_job,
    ARCHIVE_ROOT,
    DUPLICATE_ROOT,
)
from backend.pdf_ingestion import INVALID_DOCUMENT_TYPE_ORDER, choose_invoice_share_path, process_invoice, recover_pdf_file, WATCH_PATH
import backend.invoice_lifecycle as invoice_lifecycle
import backend.pdf_ingestion as pdf_ingestion
import backend.review_api as review_api

# Test directories
TEST_WATCH_PATH = r"C:\Aradhana\Test_InvoicePDFs"
TEST_ARCHIVE_ROOT = r"C:\Aradhana\Test_OLD"
TEST_DUPLICATE_ROOT = r"C:\Aradhana\Test_DUPLICATE"

def reset_ingestion_status_counters():
    for key in [
        "total_files_seen",
        "current_scan_processed",
        "invoices_inserted",
        "inserted_today",
        "skipped_existing",
        "skipped_duplicates",
        "invalid_documents",
        "invalid_document_count",
        "duplicate_move_failed_permission",
        "duplicate_archive_permission_count",
        "duplicate_ignored_until_permission_fixed",
        "parse_failures",
        "actual_errors",
        "warnings",
        "failed_files",
    ]:
        pdf_ingestion.ingestion_status[key] = 0
    pdf_ingestion.ingestion_status["duplicate_permission_message"] = None
    pdf_ingestion.ingestion_status["last_error"] = None

@pytest.fixture(scope="module")
def db():
    # Setup test database
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield db
    db.close()
    # Base.metadata.drop_all(bind=engine)

def test_duplicate_detection(db, tmp_path, monkeypatch):
    # This is a bit complex to test without real PDFs, but we can test the handle_duplicate function
    monkeypatch.setattr(invoice_lifecycle, "DUPLICATE_ROOT", str(tmp_path / "dups"))
    os.makedirs(invoice_lifecycle.DUPLICATE_ROOT, exist_ok=True)
    test_file = os.path.join(str(tmp_path), "test_dup.pdf")
    with open(test_file, "w") as f:
        f.write("test content")
    
    initial_dups = len(os.listdir(invoice_lifecycle.DUPLICATE_ROOT))
    handle_duplicate(test_file, db, reason="Test Duplicate")
    
    assert len(os.listdir(invoice_lifecycle.DUPLICATE_ROOT)) == initial_dups + 1
    
    # Check audit log
    log = db.query(AuditLog).filter(AuditLog.action == "DUPLICATE_MOVE").first()
    assert log is not None
    assert "Test Duplicate" in log.metadata_json

def test_duplicate_access_denied_is_logged_once_and_file_untouched(db, tmp_path, monkeypatch):
    test_file = tmp_path / "permission_dup.pdf"
    test_file.write_text("duplicate content")
    file_hash = f"hash-{datetime.now().timestamp()}"

    def deny_move(_src, _dst):
        raise PermissionError("Access is denied")

    monkeypatch.setattr(invoice_lifecycle, "DUPLICATE_ROOT", str(tmp_path / "dups"))
    monkeypatch.setattr(shutil, "move", deny_move)

    first = handle_duplicate(str(test_file), db, reason="Permission Duplicate", file_hash=file_hash)
    second = handle_duplicate(str(test_file), db, reason="Permission Duplicate", file_hash=file_hash)

    assert first["status"] == "permission_failed"
    assert first["action"] == DUPLICATE_MOVE_FAILED_PERMISSION
    assert second["status"] == "ignored_permission"
    assert test_file.exists()

    matching_logs = [
        log for log in db.query(AuditLog).filter(AuditLog.action == DUPLICATE_MOVE_FAILED_PERMISSION).all()
        if file_hash in (log.metadata_json or "")
    ]
    assert len(matching_logs) == 1
    assert DUPLICATE_PERMISSION_OPERATOR_MESSAGE in matching_logs[0].metadata_json

def test_process_invoice_duplicate_access_denied_does_not_create_invoice_or_retry(db, tmp_path, monkeypatch):
    reset_ingestion_status_counters()
    unique_no = f"TEST-DUP-LOOP-{datetime.now().timestamp()}"
    file_hash = f"hash-loop-{datetime.now().timestamp()}"
    test_file = tmp_path / "loop_dup.pdf"
    test_file.write_text("duplicate content")
    existing = Bill(
        bill_number=unique_no,
        total_amount=100.0,
        status="Green",
        pdf_hash=file_hash,
        pdf_path=str(tmp_path / "existing.pdf"),
    )
    db.add(existing)
    db.commit()

    move_attempts = {"count": 0}

    def deny_archive_copy(_src, _dst):
        move_attempts["count"] += 1
        raise PermissionError("Access is denied")

    monkeypatch.setattr(invoice_lifecycle, "DUPLICATE_ROOT", str(tmp_path / "dups"))
    monkeypatch.setattr(invoice_lifecycle, "DUPLICATE_FALLBACK_ROOT", None)
    monkeypatch.setattr(pdf_ingestion, "get_file_hash", lambda _path: file_hash)
    monkeypatch.setattr(invoice_lifecycle, "_verified_copy", deny_archive_copy)

    before_count = db.query(Bill).count()
    process_invoice(str(test_file))
    process_invoice(str(test_file))
    after_count = db.query(Bill).count()

    assert move_attempts["count"] == 1
    assert test_file.exists()
    assert after_count == before_count
    assert pdf_ingestion.ingestion_status["failed_files"] == 0

def test_duplicate_permission_failure_uses_fallback_quarantine_and_keeps_original(db, tmp_path, monkeypatch):
    test_file = tmp_path / "permission_fallback.pdf"
    test_file.write_text("duplicate content")
    file_hash = f"hash-fallback-{datetime.now().timestamp()}"
    primary_root = tmp_path / "share_duplicate"
    fallback_root = tmp_path / "local_quarantine"

    def guarded_copy(src, dst):
        if str(dst).startswith(str(primary_root)):
            raise PermissionError("Access is denied")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    monkeypatch.setattr(invoice_lifecycle, "DUPLICATE_ROOT", str(primary_root))
    monkeypatch.setattr(invoice_lifecycle, "DUPLICATE_FALLBACK_ROOT", str(fallback_root))
    monkeypatch.setattr(invoice_lifecycle, "_verified_copy", guarded_copy)

    result = handle_duplicate(str(test_file), db, reason="Permission Duplicate", file_hash=file_hash)

    assert result["status"] == "fallback_copied_permission_failed"
    assert result["action"] == DUPLICATE_MOVE_FAILED_PERMISSION
    assert result["operator_message"] == DUPLICATE_PERMISSION_OPERATOR_MESSAGE
    assert test_file.exists()
    assert result["fallback_quarantine_path"]
    assert os.path.exists(result["fallback_quarantine_path"])
    assert os.path.basename(result["fallback_quarantine_path"]).endswith("permission_fallback.pdf")

def test_duplicate_archive_permission_is_warning_not_failure_and_deduped(db, tmp_path, monkeypatch):
    reset_ingestion_status_counters()
    test_file = tmp_path / "permission_warning.pdf"
    test_file.write_text("duplicate content")
    file_hash = f"hash-warning-{datetime.now().timestamp()}"

    monkeypatch.setattr(invoice_lifecycle, "DUPLICATE_ROOT", str(tmp_path / "dups"))
    monkeypatch.setattr(invoice_lifecycle, "DUPLICATE_FALLBACK_ROOT", None)
    monkeypatch.setattr(invoice_lifecycle, "_verified_copy", lambda _src, _dst: (_ for _ in ()).throw(PermissionError("Access is denied")))

    first = handle_duplicate(str(test_file), db, reason="Permission Duplicate", file_hash=file_hash)
    pdf_ingestion.record_duplicate_result(first)
    second = handle_duplicate(str(test_file), db, reason="Permission Duplicate", file_hash=file_hash)
    pdf_ingestion.record_duplicate_result(second)

    assert first["status"] == "permission_failed"
    assert second["status"] == "ignored_permission"
    assert pdf_ingestion.ingestion_status["duplicate_archive_permission_count"] == 1
    assert pdf_ingestion.ingestion_status["warnings"] == 1
    assert pdf_ingestion.ingestion_status["failed_files"] == 0
    assert pdf_ingestion.ingestion_status["duplicate_permission_message"] == DUPLICATE_PERMISSION_OPERATOR_MESSAGE

def test_365_day_guard_blocks_deletion_of_protected_pdf(tmp_path):
    protected_pdf = tmp_path / "protected.pdf"
    protected_pdf.write_text("protected")

    with pytest.raises(PermissionError) as exc_info:
        assert_can_delete_pdf(str(protected_pdf), created_at=datetime.now())

    assert str(PDF_RETENTION_DAYS) in str(exc_info.value)

def test_archive_job_does_not_hard_delete_protected_pdf(db, tmp_path, monkeypatch):
    test_watch = tmp_path / "watch_retention"
    test_archive = tmp_path / "archive_retention"
    test_watch.mkdir()
    test_archive.mkdir()
    monkeypatch.setattr(invoice_lifecycle, "ARCHIVE_ROOT", str(test_archive))

    unique_no = f"TEST-RETENTION-{datetime.now().timestamp()}"
    pdf_path = test_watch / "protected_arch.pdf"
    pdf_path.write_text("protected archive content")
    bill = Bill(
        bill_number=unique_no,
        total_amount=100.0,
        status="Green",
        pdf_path=str(pdf_path),
        created_at=datetime.now(),
    )
    db.add(bill)
    db.commit()

    run_archive_job()
    db.refresh(bill)

    assert os.path.exists(str(pdf_path))
    assert bill.pdf_path == str(pdf_path)

def test_order_document_rejected_as_ingestion_exception_without_bill_payment_or_legacy_email(db, tmp_path, monkeypatch):
    test_file = tmp_path / "FA_253.pdf"
    test_file.write_text("Order No: RO-186\nCustomer: SANGEETA SHAH\nAdvance: 6507")
    file_hash = f"hash-order-{datetime.now().timestamp()}"
    email_calls = {"count": 0}

    def fake_parse_pdf(_path):
        return {
            "raw_text": "Order No: RO-186\nCustomer: SANGEETA SHAH\nAdvance: 6507",
            "bill_number": None,
            "ingestion_exception_reason": INVALID_DOCUMENT_TYPE_ORDER,
            "invalid_document_identifier": "RO-186",
        }

    def fake_red_email(*_args, **_kwargs):
        email_calls["count"] += 1

    monkeypatch.setattr(pdf_ingestion, "get_file_hash", lambda _path: file_hash)
    monkeypatch.setattr(pdf_ingestion, "parse_pdf", fake_parse_pdf)
    import backend.email_notifier as email_notifier
    monkeypatch.setattr(email_notifier, "send_red_alert_email", fake_red_email)

    before_bills = db.query(Bill).count()
    before_payments = db.query(Payment).count()

    process_invoice(str(test_file))
    db.expire_all()

    assert db.query(Bill).count() == before_bills
    assert db.query(Payment).count() == before_payments
    assert email_calls["count"] == 0
    exception_log = db.query(AuditLog).filter(
        AuditLog.action == INVALID_DOCUMENT_TYPE_ORDER,
        AuditLog.metadata_json.like("%FA_253.pdf%"),
        AuditLog.metadata_json.like("%RO-186%"),
    ).first()
    assert exception_log is not None
    assert pdf_ingestion.ingestion_status["last_ingestion_exception"]["reason"] == INVALID_DOCUMENT_TYPE_ORDER

def test_recover_pdf_skips_order_document_with_clear_reason(tmp_path, monkeypatch):
    test_file = tmp_path / "order_doc.pdf"
    test_file.write_text("Order No: RO-186")
    process_calls = {"count": 0}

    monkeypatch.setattr(pdf_ingestion, "get_file_hash", lambda _path: "hash-recover-order")
    monkeypatch.setattr(pdf_ingestion, "parse_pdf", lambda _path: {
        "raw_text": "Order No: RO-186",
        "bill_number": None,
        "ingestion_exception_reason": INVALID_DOCUMENT_TYPE_ORDER,
        "invalid_document_identifier": "RO-186",
    })
    monkeypatch.setattr(pdf_ingestion, "process_invoice", lambda _path: process_calls.__setitem__("count", process_calls["count"] + 1))

    result = recover_pdf_file(str(test_file))

    assert result["status"] == "skipped"
    assert result["reason"] == INVALID_DOCUMENT_TYPE_ORDER
    assert process_calls["count"] == 0

def test_recover_pdf_accepts_valid_invoice_pdf(tmp_path, monkeypatch):
    test_file = tmp_path / "valid_invoice.pdf"
    test_file.write_text("Invoice No: FA-253")
    process_calls = {"count": 0}

    monkeypatch.setattr(pdf_ingestion, "get_file_hash", lambda _path: "hash-recover-valid")
    monkeypatch.setattr(pdf_ingestion, "parse_pdf", lambda _path: {
        "raw_text": "Invoice No: FA-253",
        "bill_number": "FA-253",
        "ingestion_exception_reason": None,
    })
    monkeypatch.setattr(pdf_ingestion, "process_invoice", lambda _path: process_calls.__setitem__("count", process_calls["count"] + 1))

    result = recover_pdf_file(str(test_file))

    assert result["status"] == "accepted"
    assert result["bill_number"] == "FA-253"
    assert process_calls["count"] == 1

def test_invoice_pdf_missing_bill_returns_invalid_missing_invoice_record(db):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(review_api.get_invoice_pdf(999999999, db=db))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Invalid/missing invoice record"

def test_invoice_pdf_valid_bill_returns_pdf_response(db, tmp_path):
    pdf_path = tmp_path / "valid_bill.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%test\n")
    unique_no = f"TEST-PDF-VIEW-{datetime.now().timestamp()}"
    bill = Bill(
        bill_number=unique_no,
        total_amount=100.0,
        status="Yellow",
        pdf_path=str(pdf_path),
        created_at=datetime.now(),
    )
    db.add(bill)
    db.commit()

    response = asyncio.run(review_api.get_invoice_pdf(bill.id, db=db))

    assert response.media_type == "application/pdf"
    assert response.path == str(pdf_path)

def test_invoice_pdf_missing_file_returns_clear_file_missing_reason(db, tmp_path):
    missing_path = tmp_path / "missing_bill.pdf"
    unique_no = f"TEST-PDF-MISSING-{datetime.now().timestamp()}"
    bill = Bill(
        bill_number=unique_no,
        total_amount=100.0,
        status="Yellow",
        pdf_path=str(missing_path),
        created_at=datetime.now(),
    )
    db.add(bill)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(review_api.get_invoice_pdf(bill.id, db=db))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "PDF file missing on disk"

def test_invoice_share_primary_access_denied_fallback_works(monkeypatch):
    primary = r"\\PC2\AradhanaInvoicePDFs"
    fallback = r"I:\\"

    def fake_exists(path):
        return path == fallback

    def fake_listdir(path):
        if path == primary:
            raise PermissionError("[WinError 5] Access is denied")
        if path == fallback:
            return ["FA_1.pdf", "notes.txt", "FA_2.PDF"]
        raise FileNotFoundError(path)

    monkeypatch.setattr(pdf_ingestion.os.path, "exists", fake_exists)
    monkeypatch.setattr(pdf_ingestion.os, "listdir", fake_listdir)

    result = choose_invoice_share_path(primary=primary, fallback=fallback)

    assert result["accessible"] is True
    assert result["path"] == fallback
    assert result["source"] == "fallback"
    assert result["pdf_count"] == 2
    assert "PermissionError" in result["errors"][0]["error"]

def test_invoice_share_both_inaccessible_returns_red_reason(monkeypatch):
    primary = r"\\PC2\AradhanaInvoicePDFs"
    fallback = r"I:\\"

    monkeypatch.setattr(pdf_ingestion.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(pdf_ingestion.os, "listdir", lambda path: (_ for _ in ()).throw(PermissionError(f"{path} denied")))

    result = choose_invoice_share_path(primary=primary, fallback=fallback)

    assert result["accessible"] is False
    assert result["path"] == primary
    assert result["source"] is None
    assert len(result["errors"]) == 2
    assert all("PermissionError" in error["error"] for error in result["errors"])

def test_watcher_pdf_count_uses_chosen_path(monkeypatch):
    chosen = r"I:\\"

    monkeypatch.setattr(pdf_ingestion, "WATCH_PATH", chosen)
    monkeypatch.setattr(pdf_ingestion.os.path, "exists", lambda path: path == chosen)
    monkeypatch.setattr(pdf_ingestion.os, "listdir", lambda path: ["one.pdf", "two.PDF", "readme.txt"])

    assert pdf_ingestion.check_share_health() is True
    assert pdf_ingestion.ingestion_status["path_exists"] is True
    assert pdf_ingestion.ingestion_status["pdf_files_found"] == 2
    assert pdf_ingestion.ingestion_status["last_error"] is None

def test_scan_updates_last_scan_when_all_files_skipped(monkeypatch):
    reset_ingestion_status_counters()
    chosen = r"I:\\"

    monkeypatch.setattr(pdf_ingestion, "WATCH_PATH", chosen)
    monkeypatch.setattr(pdf_ingestion.os.path, "exists", lambda path: path == chosen)
    monkeypatch.setattr(pdf_ingestion.os, "listdir", lambda path: ["one.pdf", "two.pdf"])
    monkeypatch.setattr(pdf_ingestion, "process_invoice", lambda _path: {"status": "skipped_existing"})
    monkeypatch.setattr(pdf_ingestion, "_count_inserted_today", lambda: 0)

    summary = pdf_ingestion.perform_scan()

    assert summary["scan_started_at"]
    assert summary["scan_completed_at"]
    assert summary["files_seen"] == 2
    assert summary["processed"] == 2
    assert summary["inserted"] == 0
    assert summary["skipped_existing"] == 2
    assert pdf_ingestion.ingestion_status["last_scan_started_at"] == summary["scan_started_at"]
    assert pdf_ingestion.ingestion_status["last_scan_completed_at"] == summary["scan_completed_at"]
    assert pdf_ingestion.ingestion_status["current_scan_processed"] == 2

def test_scan_failed_count_only_true_parse_or_system_errors(monkeypatch):
    reset_ingestion_status_counters()
    chosen = r"I:\\"
    results = iter([
        {"status": "skipped_existing", "warning": True},
        {"status": "invalid_document"},
        {"status": "parse_failure"},
        {"status": "error"},
    ])

    monkeypatch.setattr(pdf_ingestion, "WATCH_PATH", chosen)
    monkeypatch.setattr(pdf_ingestion.os.path, "exists", lambda path: path == chosen)
    monkeypatch.setattr(pdf_ingestion.os, "listdir", lambda path: ["dup.pdf", "order.pdf", "bad.pdf", "system.pdf"])
    monkeypatch.setattr(pdf_ingestion, "process_invoice", lambda _path: next(results))
    monkeypatch.setattr(pdf_ingestion, "_count_inserted_today", lambda: 0)

    summary = pdf_ingestion.perform_scan()

    assert summary["warnings"] == 1
    assert summary["invalid_documents"] == 1
    assert summary["parse_failures"] == 1
    assert summary["errors"] == 1
    assert pdf_ingestion.ingestion_status["warnings"] == 1
    assert pdf_ingestion.ingestion_status["invalid_documents"] == 1
    assert pdf_ingestion.ingestion_status["failed_files"] == 2

def test_sync_now_response_contains_scan_timestamps(monkeypatch):
    expected = {
        "scan_started_at": "2026-06-06T10:00:00",
        "scan_completed_at": "2026-06-06T10:00:01",
        "files_seen": 0,
        "inserted": 0,
        "skipped_existing": 0,
        "invalid_documents": 0,
        "warnings": 0,
        "errors": 0,
    }
    monkeypatch.setattr(review_api, "perform_scan", lambda: expected)

    result = asyncio.run(review_api.trigger_scan())

    assert result == expected

def test_archive_job(db, tmp_path, monkeypatch):
    test_watch = tmp_path / "watch"
    test_archive = tmp_path / "archive"
    test_watch.mkdir()
    test_archive.mkdir()
    monkeypatch.setattr(invoice_lifecycle, "ARCHIVE_ROOT", str(test_archive))
    # Create a bill with Green status
    unique_no = f"TEST-ARCH-{datetime.now().timestamp()}"
    bill = Bill(
        bill_number=unique_no,
        total_amount=100.0,
        status="Green",
        pdf_path=os.path.join(str(test_watch), "test_arch.pdf"),
        created_at=datetime.now() - timedelta(days=PDF_RETENTION_DAYS + 1),
    )
    with open(bill.pdf_path, "w") as f:
        f.write("test content")
    old_timestamp = (datetime.now() - timedelta(days=PDF_RETENTION_DAYS + 1)).timestamp()
    os.utime(bill.pdf_path, (old_timestamp, old_timestamp))
    
    db.add(bill)
    db.commit()
    
    run_archive_job()
    
    # Check if file moved
    db.refresh(bill)
    assert str(test_archive) in bill.pdf_path
    assert os.path.exists(bill.pdf_path)
    assert not os.path.exists(os.path.join(str(test_watch), "test_arch.pdf"))
