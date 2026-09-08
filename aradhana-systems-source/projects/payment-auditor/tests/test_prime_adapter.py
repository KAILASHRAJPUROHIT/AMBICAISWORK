import pytest
from backend.prime_adapter import parse_prime_customer, parse_prime_bill, parse_prime_payment, parse_prime_cheque

def test_valid_prime_customer():
    raw = {"cust_id": "P1", "name": "Alice", "phone": "999", "location": "NY"}
    record = parse_prime_customer(raw)
    assert record.customer_id == "P1"
    assert record.customer_name == "Alice"

def test_valid_prime_bill():
    raw = {"invoice_no": "INV1", "client_ref": "P1", "total_val": "100.5", "inv_date": "2026-05-05", "status": "Shipped"}
    record = parse_prime_bill(raw)
    assert record.bill_id == "INV1"
    assert record.amount == 100.5

def test_valid_prime_payment():
    raw = {"txn_id": "TXN1", "invoice_no": "INV1", "val": "100.5", "type": "NEFT", "utr": "REF123", "date": "2026-05-06"}
    record = parse_prime_payment(raw)
    assert record.payment_id == "TXN1"
    assert record.utr_reference == "REF123"

def test_valid_prime_cheque():
    raw = {"chq_id": "CHQ1", "invoice_no": "INV1", "chq_no": "000111", "bank": "SBI", "val": "100.5", "dep_date": "2026-05-06", "status": "Cleared"}
    record = parse_prime_cheque(raw)
    assert record.cheque_id == "CHQ1"
    assert record.amount == 100.5

def test_missing_required_field():
    raw = {"cust_id": "P1", "name": "Alice"} # missing phone and location
    with pytest.raises(KeyError):
        parse_prime_customer(raw)

def test_malformed_erp_record():
    raw = {"invoice_no": "INV1", "client_ref": "P1", "total_val": "not_a_number", "inv_date": "2026-05-05", "status": "Shipped"}
    with pytest.raises(ValueError):
        parse_prime_bill(raw)
