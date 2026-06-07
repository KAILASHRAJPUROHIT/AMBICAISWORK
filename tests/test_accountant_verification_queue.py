from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.review_api as review_api
from backend.auth_service import hash_password
from backend.database import Base
from backend.models import AccountantVerificationQueue, AuditLog, Bill, Payment, User
from scripts.backfill_accountant_verification_queue import run_backfill


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def seed_users(db):
    db.add_all([
        User(employee_id="OWNER-01", name="Owner", role="OWNER", hashed_password=hash_password("owner"), is_active=1),
        User(employee_id="ACC-01", name="Accountant", role="ACCOUNTANT", hashed_password=hash_password("acc"), is_active=1),
        User(employee_id="STAFF-01", name="Staff", role="STAFF", hashed_password=hash_password("staff"), is_active=1),
    ])
    db.commit()


def seed_bill(db, bill_number="SS-QUEUE", status="Yellow", review_required=1, is_test_data=False):
    bill = Bill(
        bill_number=bill_number,
        customer_name="Queue Customer",
        amount=11000,
        payment_mode="UPI",
        status=status,
        review_required=review_required,
        is_test_data=is_test_data,
        invoice_date=datetime(2026, 6, 7, 15, 0),
        created_at=datetime(2026, 6, 7, 10, 0),
    )
    db.add(bill)
    db.flush()
    db.add(Payment(
        bill_id=bill.id,
        amount=11000,
        mode="UPI",
        status="Yellow",
        utr_reference=None,
        payment_date=None,
        created_at=datetime(2026, 6, 7, 10, 0),
    ))
    db.commit()
    return bill.id


def make_client(monkeypatch, db):
    bind = db.get_bind()
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=bind)

    def override_get_db():
        local_db = TestingSessionLocal()
        try:
            yield local_db
        finally:
            local_db.close()

    def fake_validate_session(_db, token):
        if token == "owner-token":
            return "OWNER-01"
        if token == "accountant-token":
            return "ACC-01"
        if token == "staff-token":
            return "STAFF-01"
        return None

    review_api.app.dependency_overrides.clear()
    monkeypatch.setitem(review_api.app.dependency_overrides, review_api.get_db, override_get_db)
    monkeypatch.setattr(review_api, "validate_session", fake_validate_session)
    return TestClient(review_api.app)


def test_backfill_default_dry_run_does_not_write_queue_or_audit():
    db = make_db()
    seed_bill(db)

    summary = run_backfill(db, apply=False, now=datetime(2026, 6, 7, 11, 0))

    assert summary["mode"] == "DRY_RUN"
    assert summary["candidates"] == 1
    assert summary["would_create"] == 1
    assert db.query(AccountantVerificationQueue).count() == 0
    assert db.query(AuditLog).count() == 0


def test_backfill_apply_creates_queue_and_audit_without_bill_or_payment_mutation():
    db = make_db()
    bill_id = seed_bill(db)

    summary = run_backfill(db, apply=True, now=datetime(2026, 6, 7, 11, 0))

    assert summary["mode"] == "APPLY"
    assert summary["created"] == 1
    queue_item = db.query(AccountantVerificationQueue).one()
    assert queue_item.bill_id == bill_id
    assert queue_item.invoice_no == "SS-QUEUE"
    assert queue_item.queue_status == "OPEN"
    assert queue_item.payment_status == "REVIEW_REQUIRED"
    assert queue_item.proof_status == "NO_PROOF"
    assert db.query(AuditLog).filter(AuditLog.action == "ACCOUNTANT_VERIFICATION_QUEUED").count() == 1

    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    payment = db.query(Payment).filter(Payment.bill_id == bill_id).first()
    assert bill.status == "Yellow"
    assert payment.status == "Yellow"
    assert payment.utr_reference is None


def test_backfill_excludes_test_archive_hardening_data():
    db = make_db()
    seed_bill(db, bill_number="TEST-001")
    seed_bill(db, bill_number="ARCH-001")
    seed_bill(db, bill_number="HARDENING-001")
    seed_bill(db, bill_number="SS-REAL")

    summary = run_backfill(db, apply=False, now=datetime(2026, 6, 7, 11, 0))

    assert summary["candidates"] == 1
    assert summary["rows"][0]["invoice_no"] == "SS-REAL"


def test_get_accountant_verification_requires_auth(monkeypatch):
    db = make_db()
    seed_users(db)
    client = make_client(monkeypatch, db)

    response = client.get("/api/escalations/accountant-verification")

    assert response.status_code == 401


def test_get_accountant_verification_allows_accountant_and_returns_empty_array(monkeypatch):
    db = make_db()
    seed_users(db)
    client = make_client(monkeypatch, db)

    response = client.get(
        "/api/escalations/accountant-verification",
        headers={"X-Session-Token": "accountant-token"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_get_accountant_verification_blocks_staff(monkeypatch):
    db = make_db()
    seed_users(db)
    client = make_client(monkeypatch, db)

    response = client.get(
        "/api/escalations/accountant-verification",
        headers={"X-Session-Token": "staff-token"},
    )

    assert response.status_code == 403


def test_get_accountant_verification_returns_queue_rows(monkeypatch):
    db = make_db()
    seed_users(db)
    seed_bill(db, bill_number="SS-LIST")
    run_backfill(db, apply=True, now=datetime(2026, 6, 7, 11, 0))
    client = make_client(monkeypatch, db)

    response = client.get(
        "/api/escalations/accountant-verification",
        headers={"X-Session-Token": "owner-token"},
    )

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["invoice_no"] == "SS-LIST"
    assert rows[0]["payment_status"] == "REVIEW_REQUIRED"
    assert rows[0]["queue_status"] == "OPEN"
    assert "remaining_seconds" in rows[0]
