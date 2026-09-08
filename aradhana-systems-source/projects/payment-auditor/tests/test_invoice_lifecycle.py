import os
import shutil
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.database import SessionLocal, Base, engine
from backend.models import Bill, AuditLog
from backend.invoice_lifecycle import (
    DUPLICATE_MOVE_FAILED_PERMISSION,
    DUPLICATE_PERMISSION_MESSAGE,
    handle_duplicate,
    run_archive_job,
    ARCHIVE_ROOT,
    DUPLICATE_ROOT,
)
from backend.pdf_ingestion import process_invoice, WATCH_PATH
import backend.invoice_lifecycle as invoice_lifecycle
import backend.pdf_ingestion as pdf_ingestion

# Test directories
TEST_WATCH_PATH = r"C:\Aradhana\Test_InvoicePDFs"
TEST_ARCHIVE_ROOT = r"C:\Aradhana\Test_OLD"
TEST_DUPLICATE_ROOT = r"C:\Aradhana\Test_DUPLICATE"

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
    assert DUPLICATE_PERMISSION_MESSAGE in matching_logs[0].metadata_json

def test_process_invoice_duplicate_access_denied_does_not_create_invoice_or_retry(db, tmp_path, monkeypatch):
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

    def deny_move(_src, _dst):
        move_attempts["count"] += 1
        raise PermissionError("Access is denied")

    monkeypatch.setattr(invoice_lifecycle, "DUPLICATE_ROOT", str(tmp_path / "dups"))
    monkeypatch.setattr(pdf_ingestion, "get_file_hash", lambda _path: file_hash)
    monkeypatch.setattr(shutil, "move", deny_move)

    before_count = db.query(Bill).count()
    process_invoice(str(test_file))
    process_invoice(str(test_file))
    after_count = db.query(Bill).count()

    assert move_attempts["count"] == 1
    assert test_file.exists()
    assert after_count == before_count

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
        pdf_path=os.path.join(str(test_watch), "test_arch.pdf")
    )
    with open(bill.pdf_path, "w") as f:
        f.write("test content")
    
    db.add(bill)
    db.commit()
    
    run_archive_job()
    
    # Check if file moved
    db.refresh(bill)
    assert str(test_archive) in bill.pdf_path
    assert os.path.exists(bill.pdf_path)
    assert not os.path.exists(os.path.join(str(test_watch), "test_arch.pdf"))
