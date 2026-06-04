import os
import shutil
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.database import SessionLocal, Base, engine
from backend.models import Bill, AuditLog

@pytest.fixture(scope="module")
def db():
    # Setup test database
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield db
    db.close()
    # Base.metadata.drop_all(bind=engine)

def test_duplicate_detection(db, tmp_path, monkeypatch):
    import backend.invoice_lifecycle as il
    test_watch = tmp_path / "WATCH"
    test_dup = tmp_path / "DUP"
    test_watch.mkdir()
    test_dup.mkdir()
    
    monkeypatch.setattr(il, "WATCH_PATH", str(test_watch))
    monkeypatch.setattr(il, "DUPLICATE_ROOT", str(test_dup))
    
    test_file = os.path.join(str(test_watch), "test_dup.pdf")
    with open(test_file, "w") as f:
        f.write("test content")
    
    initial_dups = len(os.listdir(str(test_dup)))
    il.handle_duplicate(test_file, db, reason="Test Duplicate")

    assert len(os.listdir(str(test_dup))) == initial_dups # No file moved per new mandate

    # Verify Audit Log was created
    log = db.query(AuditLog).filter(AuditLog.action == "DUPLICATE_DETECTED").order_by(AuditLog.id.desc()).first()
    assert log is not None
    assert "Test Duplicate" in log.metadata_json

def test_archive_job(db, tmp_path, monkeypatch):
    import backend.invoice_lifecycle as il
    test_watch = tmp_path / "WATCH"
    test_arch = tmp_path / "ARCH"
    test_watch.mkdir(exist_ok=True)
    test_arch.mkdir(exist_ok=True)
    
    monkeypatch.setattr(il, "WATCH_PATH", str(test_watch))
    monkeypatch.setattr(il, "ARCHIVE_ROOT", str(test_arch))
    
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
    
    il.run_archive_job()
    
    # Check if file moved
    db.refresh(bill)
    assert str(test_arch) in bill.pdf_path
    assert os.path.exists(bill.pdf_path)
    assert os.path.exists(os.path.join(str(test_watch), "test_arch.pdf")) # Original kept