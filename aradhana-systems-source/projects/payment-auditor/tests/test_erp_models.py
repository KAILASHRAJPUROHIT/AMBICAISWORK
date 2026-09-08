import pytest
from pydantic import ValidationError
from backend.erp_models import CustomerRecord, BillRecord, PaymentRecord, ChequeRecord

def test_valid_customer_record():
    customer = CustomerRecord(
        customer_id="CUST-001",
        customer_name="John Doe",
        mobile="9876543210",
        city="Mumbai"
    )
    assert customer.customer_id == "CUST-001"
    assert customer.customer_name == "John Doe"
    assert customer.mobile == "9876543210"
    assert customer.city == "Mumbai"

def test_valid_bill_record():
    bill = BillRecord(
        bill_id="BILL-123",
        customer_id="CUST-001",
        amount=1500.50,
        bill_date="2026-05-20",
        delivery_status="Delivered"
    )
    assert bill.bill_id == "BILL-123"
    assert bill.amount == 1500.50

def test_valid_payment_record():
    payment = PaymentRecord(
        payment_id="PAY-999",
        bill_id="BILL-123",
        amount=1500.50,
        payment_mode="NEFT",
        utr_reference="SBIN0000000",
        payment_date="2026-05-21"
    )
    assert payment.payment_id == "PAY-999"
    assert payment.payment_mode == "NEFT"

def test_valid_cheque_record():
    cheque = ChequeRecord(
        cheque_id="CHQ-444",
        bill_id="BILL-123",
        cheque_number="000123",
        bank_name="HDFC",
        amount=1500.50,
        deposit_date="2026-05-22",
        clearance_status="Pending"
    )
    assert cheque.cheque_number == "000123"
    assert cheque.clearance_status == "Pending"

def test_validation_failures():
    # Missing required fields
    with pytest.raises(ValidationError):
        CustomerRecord(customer_id="CUST-002")
    
    # Invalid type that cannot be coerced (dict instead of float)
    with pytest.raises(ValidationError):
        BillRecord(
            bill_id="BILL-124",
            customer_id="CUST-002",
            amount={"invalid": "type"},
            bill_date="2026-05-20",
            delivery_status="Pending"
        )
