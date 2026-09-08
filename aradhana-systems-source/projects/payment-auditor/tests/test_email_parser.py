import pytest
from backend.email_parser import parse_bank_email

def test_hdfc_email():
    subject = "HDFC Bank: You have received a payment"
    body = "Dear Customer, a payment of Rs. 10,500.00 has been credited to your account. UTR: N123456789012. Date: 12/05/2026."
    parsed = parse_bank_email(subject, body)
    assert parsed.amount == 10500.0
    assert parsed.utr_reference == "N123456789012"
    assert parsed.transaction_date == "12/05/2026"
    assert parsed.sender_bank == "HDFC"
    assert parsed.raw_subject == subject
    assert parsed.raw_body == body

def test_icici_email():
    subject = "Transaction Alert from ICICI Bank"
    body = "INR 5000.50 credited. Ref No: ICI987654321. Date: 15 May 2026"
    parsed = parse_bank_email(subject, body)
    assert parsed.amount == 5000.5
    assert parsed.utr_reference == "ICI987654321"
    assert parsed.transaction_date == "15 May 2026"
    assert parsed.sender_bank == "ICICI"

def test_sbi_email():
    subject = "SBI Alert"
    body = "Rs 1,000 deposited. UTR Number: SBIN000123456. On 10-05-2026"
    parsed = parse_bank_email(subject, body)
    assert parsed.amount == 1000.0
    assert parsed.utr_reference == "SBIN000123456"
    assert parsed.transaction_date == "10-05-2026"
    assert parsed.sender_bank == "SBI"

def test_missing_utr():
    subject = "Payment received"
    body = "Amount Rs. 200 credited on 01/01/2026"
    parsed = parse_bank_email(subject, body)
    assert parsed.amount == 200.0
    assert parsed.utr_reference is None
    assert parsed.transaction_date == "01/01/2026"
    assert parsed.sender_bank is None

def test_malformed_email():
    subject = "Spam email"
    body = "Win a free lottery! Click here."
    parsed = parse_bank_email(subject, body)
    assert parsed.amount is None
    assert parsed.utr_reference is None
    assert parsed.transaction_date is None
    assert parsed.sender_bank is None
    assert parsed.raw_subject == subject
    assert parsed.raw_body == body
