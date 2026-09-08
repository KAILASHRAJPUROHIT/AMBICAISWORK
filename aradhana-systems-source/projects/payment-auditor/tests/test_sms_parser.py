import pytest
from backend.sms_parser import parse_bank_sms

def test_hdfc_sms():
    msg = "Rs. 5000.00 credited to a/c XXXXX1234 on 15/05/2026. UPI Ref: 123456789012. HDFC Bank."
    parsed = parse_bank_sms(msg)
    assert parsed.amount == 5000.0
    assert parsed.utr_reference == "123456789012"
    assert parsed.transaction_date == "15/05/2026"
    assert parsed.sender_bank == "HDFC"
    assert parsed.raw_message == msg

def test_icici_sms():
    msg = "Acct XX123 credited with INR 2000 on 16 May 2026. Ref No: ICI123456. ICICI Bank."
    parsed = parse_bank_sms(msg)
    assert parsed.amount == 2000.0
    assert parsed.utr_reference == "ICI123456"
    assert parsed.transaction_date == "16 May 2026"
    assert parsed.sender_bank == "ICICI"
    assert parsed.raw_message == msg

def test_sbi_sms():
    msg = "SBI Alert: Rs 1,500 deposited in your a/c. UTR Number: SBIN987654321 on 17-05-2026."
    parsed = parse_bank_sms(msg)
    assert parsed.amount == 1500.0
    assert parsed.utr_reference == "SBIN987654321"
    assert parsed.transaction_date == "17-05-2026"
    assert parsed.sender_bank == "SBI"
    assert parsed.raw_message == msg

def test_missing_utr():
    msg = "Rs. 100 credited on 01/01/2026 to HDFC bank."
    parsed = parse_bank_sms(msg)
    assert parsed.amount == 100.0
    assert parsed.utr_reference is None
    assert parsed.transaction_date == "01/01/2026"
    assert parsed.sender_bank == "HDFC"
    assert parsed.raw_message == msg

def test_malformed_sms():
    msg = "Happy new year from SBI!"
    parsed = parse_bank_sms(msg)
    assert parsed.amount is None
    assert parsed.utr_reference is None
    assert parsed.transaction_date is None
    assert parsed.sender_bank == "SBI"
    assert parsed.raw_message == msg
