import pytest
from backend.schemas import ParsedBankEmail, ParsedBankSMS
from backend.bank_alert_normalizer import normalize_email_alert, normalize_sms_alert

def test_normalize_email_alert():
    parsed_email = ParsedBankEmail(
        amount=10500.0,
        utr_reference="N123456789012",
        transaction_date="12/05/2026",
        sender_bank="HDFC",
        raw_subject="HDFC Bank: You have received a payment",
        raw_body="Dear Customer, a payment of Rs. 10,500.00 has been credited to your account. UTR: N123456789012."
    )
    
    normalized = normalize_email_alert(parsed_email)
    
    assert normalized.amount == 10500.0
    assert normalized.utr_reference == "N123456789012"
    assert normalized.transaction_date == "12/05/2026"
    assert normalized.sender_bank == "HDFC"
    assert normalized.source_type == "EMAIL"
    assert normalized.raw_content == f"Subject: {parsed_email.raw_subject}\nBody: {parsed_email.raw_body}"

def test_normalize_sms_alert():
    parsed_sms = ParsedBankSMS(
        amount=5000.0,
        utr_reference="123456789012",
        transaction_date="15/05/2026",
        sender_bank="HDFC",
        raw_message="Rs. 5000.00 credited to a/c XXXXX1234 on 15/05/2026. UPI Ref: 123456789012. HDFC Bank."
    )
    
    normalized = normalize_sms_alert(parsed_sms)
    
    assert normalized.amount == 5000.0
    assert normalized.utr_reference == "123456789012"
    assert normalized.transaction_date == "15/05/2026"
    assert normalized.sender_bank == "HDFC"
    assert normalized.source_type == "SMS"
    assert normalized.raw_content == parsed_sms.raw_message

def test_preserve_empty_fields():
    parsed_sms = ParsedBankSMS(
        amount=None,
        utr_reference=None,
        transaction_date=None,
        sender_bank="SBI",
        raw_message="Malformed SBI message"
    )
    
    normalized = normalize_sms_alert(parsed_sms)
    
    assert normalized.amount is None
    assert normalized.utr_reference is None
    assert normalized.transaction_date is None
    assert normalized.sender_bank == "SBI"
    assert normalized.source_type == "SMS"
    assert normalized.raw_content == "Malformed SBI message"
