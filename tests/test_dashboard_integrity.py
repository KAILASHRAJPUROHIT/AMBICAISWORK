import pytest
from datetime import datetime
from backend.reconciliation.signature import compute_payment_signature

class MockBill:
    def __init__(self, id, status, bill_number):
        self.id = id
        self.status = status
        self.bill_number = bill_number

class MockPayment:
    def __init__(self, id, mode, amount, utr, dt):
        self.id = id
        self.mode = mode
        self.amount = amount
        self.utr_reference = utr
        self.created_at = dt
        self.bill_id = 1

class MockQueue:
    def __init__(self, queue_status):
        self.queue_status = queue_status
        self.created_at = datetime.utcnow()

class MockDB:
    def __init__(self, bank_alerts=None, sms_alerts=None, queues=None):
        self.bank_alerts = bank_alerts or []
        self.sms_alerts = sms_alerts or []
        self.queues = queues or []
        
    def query(self, model):
        class MockQuery:
            def __init__(self, items):
                self.items = items
            def filter(self, *args, **kwargs):
                return self
            def order_by(self, *args, **kwargs):
                return self
            def first(self):
                return self.items[0] if self.items else None
            def all(self):
                return self.items
                
        if model.__name__ == 'BankAlert':
            return MockQuery(self.bank_alerts)
        elif model.__name__ == 'SMSAlert':
            return MockQuery(self.sms_alerts)
        elif model.__name__ == 'AccountantVerificationQueue':
            return MockQuery(self.queues)
        return MockQuery([])

def test_green_high_no_proof_is_blocked():
    db = MockDB()
    bill = MockBill(1, "Green", "B-1")
    payment = MockPayment(1, "UPI", 100, "123", datetime.utcnow())
    sig = compute_payment_signature(db, bill, [payment])
    
    assert sig["confidence"] == "Low"
    assert sig["integrity_status"] == "CONTRADICTORY_STATE"
    assert "Green bill has missing required UPI proof" in sig["warning_reason"]

def test_advance_no_approval_cannot_be_high():
    db = MockDB()
    bill = MockBill(1, "Pending", "B-2")
    payment = MockPayment(1, "ADVANCE", 500, None, datetime.utcnow())
    sig = compute_payment_signature(db, bill, [payment])
    
    assert sig["confidence"] == "Low"
    assert sig["integrity_status"] == "REVIEW_REQUIRED"
    assert sig["state"] == "Accountant Review Required"

def test_cash_only_proof_not_needed():
    db = MockDB()
    bill = MockBill(1, "Green", "B-3")
    payment = MockPayment(1, "CASH", 100, None, datetime.utcnow())
    sig = compute_payment_signature(db, bill, [payment])
    
    assert sig["proof_status"] == "Payment proof not needed"
    assert sig["confidence"] == "Medium"
    assert sig["state"] == "Green"

def test_open_queue_forces_low_review():
    q = MockQueue("OPEN")
    db = MockDB(queues=[q])
    bill = MockBill(1, "Green", "B-4")
    payment = MockPayment(1, "CASH", 100, None, datetime.utcnow())
    sig = compute_payment_signature(db, bill, [payment])
    
    assert sig["review_required"] is True
    assert sig["confidence"] == "Low"
    assert sig["state"] == "Accountant Review Required"
    assert sig["integrity_status"] == "CONTRADICTORY_STATE"

def test_verified_upi_is_high_when_green():
    class MockAlert:
        def __init__(self, utr):
            self.utr_reference = utr
            self.raw_text = "test"
            self.raw_body = "test"
            self.id = 1
            
    db = MockDB(bank_alerts=[MockAlert("123")], sms_alerts=[MockAlert("123")])
    bill = MockBill(1, "Green", "B-5")
    payment = MockPayment(1, "UPI", 100, "123", datetime.utcnow())
    sig = compute_payment_signature(db, bill, [payment])
    
    assert sig["proof_status"] == "Proof verified"
    assert sig["confidence"] == "High"
    assert sig["state"] == "Green"
    assert sig["integrity_status"] == "CONSISTENT"
