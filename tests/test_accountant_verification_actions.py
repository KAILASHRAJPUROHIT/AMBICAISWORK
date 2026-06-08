from datetime import datetime, timedelta

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


def seed_bill(db, bill_number="SS-ACTION", status="Yellow", review_required=1):
    bill = Bill(
        bill_number=bill_number,
        customer_name="Action Customer",
        amount=15000,
        payment_mode="UPI",
        status=status,
        review_required=review_required,
        is_test_data=False,
        invoice_date=datetime(2026, 6, 7, 15, 0),
        created_at=datetime(2026, 6, 7, 10, 0),
    )
    db.add(bill)
    db.flush()
    db.add(Payment(
        bill_id=bill.id,
        amount=15000,
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


def test_approve_action_success(monkeypatch):
    db = make_db()
    seed_users(db)
    bill_id = seed_bill(db)
    run_backfill(db, apply=True, now=datetime(2026, 6, 7, 11, 0))
    queue_item = db.query(AccountantVerificationQueue).one()
    client = make_client(monkeypatch, db)

    response = client.post(
        f"/api/escalations/accountant-verification/{queue_item.id}/approve",
        headers={"X-Session-Token": "accountant-token"},
        json={"action_note": "Looks good to me."}
    )

    assert response.status_code == 200
    db.refresh(queue_item)
    assert queue_item.queue_status == "APPROVED"
    assert queue_item.acted_by == "ACC-01"
    assert queue_item.action_note == "Looks good to me."
    assert queue_item.acted_at is not None

    # Mutation Hardwall Check
    bill = db.query(Bill).filter(Bill.id == bill_id).one()
    payment = db.query(Payment).filter(Payment.bill_id == bill_id).one()
    assert bill.status == "Yellow"  # No mutation
    assert payment.status == "Yellow" # No mutation
    assert payment.utr_reference is None # No mutation

    # AuditLog Check
    audit = db.query(AuditLog).filter(AuditLog.action == "ACCOUNTANT_VERIFICATION_APPROVED").one()
    assert audit.entity_id == queue_item.id
    assert audit.actor == "ACC-01"


def test_reject_action_requires_note(monkeypatch):
    db = make_db()
    seed_users(db)
    seed_bill(db)
    run_backfill(db, apply=True, now=datetime(2026, 6, 7, 11, 0))
    queue_item = db.query(AccountantVerificationQueue).one()
    client = make_client(monkeypatch, db)

    # Empty note should fail
    response = client.post(
        f"/api/escalations/accountant-verification/{queue_item.id}/reject",
        headers={"X-Session-Token": "accountant-token"},
        json={"action_note": ""}
    )
    assert response.status_code == 400
    assert "Rejection requires an action note" in response.json()["detail"]


def test_reject_action_success(monkeypatch):
    db = make_db()
    seed_users(db)
    bill_id = seed_bill(db)
    run_backfill(db, apply=True, now=datetime(2026, 6, 7, 11, 0))
    queue_item = db.query(AccountantVerificationQueue).one()
    client = make_client(monkeypatch, db)

    response = client.post(
        f"/api/escalations/accountant-verification/{queue_item.id}/reject",
        headers={"X-Session-Token": "accountant-token"},
        json={"action_note": "Invalid proof provided."}
    )

    assert response.status_code == 200
    db.refresh(queue_item)
    assert queue_item.queue_status == "REJECTED"
    assert queue_item.acted_by == "ACC-01"
    assert queue_item.action_note == "Invalid proof provided."

    # Mutation Hardwall Check
    bill = db.query(Bill).filter(Bill.id == bill_id).one()
    assert bill.status == "Yellow"

    # AuditLog Check
    audit = db.query(AuditLog).filter(AuditLog.action == "ACCOUNTANT_VERIFICATION_REJECTED").one()
    assert audit.actor == "ACC-01"


def test_further_review_action_success(monkeypatch):
    db = make_db()
    seed_users(db)
    bill_id = seed_bill(db)
    run_backfill(db, apply=True, now=datetime(2026, 6, 7, 11, 0))
    queue_item = db.query(AccountantVerificationQueue).one()
    client = make_client(monkeypatch, db)

    response = client.post(
        f"/api/escalations/accountant-verification/{queue_item.id}/further-review",
        headers={"X-Session-Token": "accountant-token"},
        json={
            "action_note": "Need to call customer.",
            "deferred_until_hours": 48,
            "owner_alert_after_hours": 72
        }
    )

    assert response.status_code == 200
    db.refresh(queue_item)
    assert queue_item.queue_status == "FURTHER_REVIEW"
    assert queue_item.action_note == "Need to call customer."
    assert queue_item.deferred_until is not None
    # Roughly 48 hours from now
    diff = (queue_item.deferred_until - datetime.now()).total_seconds()
    assert 47 * 3600 < diff < 49 * 3600

    # Mutation Hardwall Check
    bill = db.query(Bill).filter(Bill.id == bill_id).one()
    assert bill.status == "Yellow"


def test_action_blocks_staff(monkeypatch):
    db = make_db()
    seed_users(db)
    seed_bill(db)
    run_backfill(db, apply=True, now=datetime(2026, 6, 7, 11, 0))
    queue_item = db.query(AccountantVerificationQueue).one()
    client = make_client(monkeypatch, db)

    response = client.post(
        f"/api/escalations/accountant-verification/{queue_item.id}/approve",
        headers={"X-Session-Token": "staff-token"},
        json={"action_note": "I am staff."}
    )

    assert response.status_code == 403


def test_action_allows_owner(monkeypatch):
    db = make_db()
    seed_users(db)
    seed_bill(db)
    run_backfill(db, apply=True, now=datetime(2026, 6, 7, 11, 0))
    queue_item = db.query(AccountantVerificationQueue).one()
    client = make_client(monkeypatch, db)

    response = client.post(
        f"/api/escalations/accountant-verification/{queue_item.id}/approve",
        headers={"X-Session-Token": "owner-token"},
        json={"action_note": "Owner approving."}
    )

    assert response.status_code == 200
    db.refresh(queue_item)
    assert queue_item.queue_status == "APPROVED"
    assert queue_item.acted_by == "OWNER-01"


def test_approve_fails_if_already_acted(monkeypatch):
    db = make_db()
    seed_users(db)
    seed_bill(db)
    run_backfill(db, apply=True, now=datetime(2026, 6, 7, 11, 0))
    queue_item = db.query(AccountantVerificationQueue).one()
    queue_item.queue_status = "APPROVED"
    db.commit()
    
    client = make_client(monkeypatch, db)

    response = client.post(
        f"/api/escalations/accountant-verification/{queue_item.id}/approve",
        headers={"X-Session-Token": "accountant-token"},
        json={"action_note": "Trying again."}
    )

    assert response.status_code == 400
    assert "already APPROVED" in response.json()["detail"]
