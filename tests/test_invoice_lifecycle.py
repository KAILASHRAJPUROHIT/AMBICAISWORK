import os
import shutil
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.database import SessionLocal, Base, engine
from backend.models import Bill, AuditLog
from backend.invoice_lifecycle import handle_duplicate, run_archive_job, ARCHIVE_ROOT, DUPLICATE_ROOT
from backend.pdf_ingestion import process_invoice, WATCH_PATH

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

def test_duplicate_detection(db):
    # This is a bit complex to test without real PDFs, but we can test the handle_duplicate function
    test_file = os.path.join(WATCH_PATH, "test_dup.pdf")
    with open(test_file, "w") as f:
        f.write("test content")
    
    initial_dups = len(os.listdir(DUPLICATE_ROOT))
    handle_duplicate(test_file, db, reason="Test Duplicate")
    
    assert len(os.listdir(DUPLICATE_ROOT)) == initial_dups + 1
    
    # Check audit log
    log = db.query(AuditLog).filter(AuditLog.action == "DUPLICATE_MOVE").first()
    assert log is not None
    assert "Test Duplicate" in log.metadata_json

def test_archive_job(db):
    # Create a bill with Green status
    unique_no = f"TEST-ARCH-{datetime.now().timestamp()}"
    bill = Bill(
        bill_number=unique_no,
        total_amount=100.0,
        status="Green",
        pdf_path=os.path.join(WATCH_PATH, "test_arch.pdf")
    )
    with open(bill.pdf_path, "w") as f:
        f.write("test content")
    
    db.add(bill)
    db.commit()
    
    run_archive_job()
    
    # Check if file moved
    db.refresh(bill)
    assert ARCHIVE_ROOT in bill.pdf_path
    assert os.path.exists(bill.pdf_path)
    assert not os.path.exists(os.path.join(WATCH_PATH, "test_arch.pdf"))
