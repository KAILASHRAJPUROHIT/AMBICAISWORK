import pytest
from fastapi.testclient import TestClient
from backend.review_api import app
from backend.database import SessionLocal
from backend.auth_service import create_user_session
from backend.models import Bill
from datetime import datetime

client = TestClient(app)


@pytest.fixture
def auth_headers():
    """Mint a real session token so requests pass the /api auth hardwall."""
    db = SessionLocal()
    try:
        token = create_user_session(db, "TEST-RUNNER")
    finally:
        db.close()
    return {"X-Session-Token": token}


def test_test_data_exclusion(auth_headers):
    db = SessionLocal()
    # Create a test bill
    test_bill = Bill(
        bill_number=f"TEST-FILTER-{datetime.now().timestamp()}",
        amount=5000.0,
        status="Yellow",
        is_test_data=True,
        invoice_date=datetime.now()
    )
    db.add(test_bill)
    
    # Create a real bill
    real_bill = Bill(
        bill_number=f"REAL-PROD-{datetime.now().timestamp()}",
        amount=1000.0,
        status="Yellow",
        is_test_data=False,
        invoice_date=datetime.now()
    )
    db.add(real_bill)
    db.commit()
    
    try:
        # Check Dashboard Stats
        response = client.get("/api/dashboard/live", headers=auth_headers)
        assert response.status_code == 200
        stats = response.json()

        # We don't know exact total but we can check if it includes our test bill
        # Actually it's easier to check the live feed

        feed_response = client.get("/api/invoices/live-feed", headers=auth_headers)
        assert feed_response.status_code == 200
        feed = feed_response.json()
        
        bill_numbers = [b["bill_number"] for b in feed]
        assert real_bill.bill_number in bill_numbers
        assert test_bill.bill_number not in bill_numbers
        
    finally:
        db.delete(test_bill)
        db.delete(real_bill)
        db.commit()
        db.close()

def test_amount_mapping_parity(auth_headers):
    db = SessionLocal()
    # SG-891 Mock parity
    # total 23672, purc 18572, net 5100
    mock_bill = Bill(
        bill_number="MOCK-SG-891",
        amount=23672.0,
        customer_purchase_amount=18572.0,
        advance_amount=0.0,
        is_test_data=False,
        invoice_date=datetime.now()
    )
    db.add(mock_bill)
    db.commit()
    
    try:
        feed_response = client.get("/api/invoices/live-feed", headers=auth_headers)
        assert feed_response.status_code == 200
        feed = feed_response.json()

        found = False
        for b in feed:
            if b["bill_number"] == "MOCK-SG-891":
                assert b["invoice_total"] == 23672.0
                assert b["cust_purc"] == 18572.0
                assert b["net_payable"] == 5100.0
                found = True
                break
        assert found is True
    finally:
        db.delete(mock_bill)
        db.commit()
        db.close()
