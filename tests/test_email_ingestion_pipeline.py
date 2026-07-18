import pytest
from datetime import datetime
from backend.schemas import RawEmail
from backend.email_ingestion_pipeline import process_email_ingestion

def test_sbi_email_ingestion():
    raw_email = RawEmail(
        message_id="sbi-123",
        sender="alerts@sbi.co.in",
        subject="Transaction Alert",
        date=datetime.now(),
        raw_body="STATE BANK: Your A/c XXXXXX1234 credited by Rs. 5000.00 on 27/10/2023. Ref No: 330012345678",
        label="BANK_SBI"
    )
    
    results = process_email_ingestion([raw_email])
    
    assert len(results) == 1
    alert = results[0]
    assert alert.amount == 5000.00
    assert alert.utr_reference == "330012345678"
    assert alert.sender_bank == "SBI"
    assert "MESSAGE_ID: sbi-123" in alert.raw_content
    assert "LABEL: BANK_SBI" in alert.raw_content

def test_icici_email_ingestion():
    raw_email = RawEmail(
        message_id="icici-456",
        sender="icicibank@icicibank.com",
        subject="Bank Alert",
        date=datetime.now(),
        raw_body="Dear Customer, transaction of INR 1,500.50 completed. UTR: ICICIR520231027001",
        label="BANK_ICICI"
    )
    
    results = process_email_ingestion([raw_email])
    
    assert len(results) == 1
    alert = results[0]
    assert alert.amount == 1500.50
    assert alert.utr_reference == "ICICIR520231027001"
    assert alert.sender_bank == "ICICI"

def test_hdfc_email_ingestion():
    raw_email = RawEmail(
        message_id="hdfc-789",
        sender="alerts@hdfcbank.net",
        subject="Credit Alert",
        date=datetime.now(),
        raw_body="HDFC Bank: Rs 25,000.00 credited to A/c XXXXXXX. Ref: HDFCR520231027999",
        label="BANK_HDFC"
    )
    
    results = process_email_ingestion([raw_email])
    
    assert len(results) == 1
    alert = results[0]
    assert alert.amount == 25000.00
    assert alert.utr_reference == "HDFCR520231027999"
    assert alert.sender_bank == "HDFC"

def test_malformed_email_handling():
    raw_email = RawEmail(
        message_id="bad-000",
        sender="unknown@test.com",
        subject="Nothing",
        date=datetime.now(),
        raw_body="Random text with no amount or UTR.",
        label="BANK_UNKNOWN"
    )
    
    results = process_email_ingestion([raw_email])
    
    assert len(results) == 1
    alert = results[0]
    assert alert.amount is None
    assert alert.utr_reference is None
    assert alert.sender_bank is None
    assert "MESSAGE_ID: bad-000" in alert.raw_content

def test_duplicate_message_id_handling():
    raw_emails = [
        RawEmail(message_id="dup-1", sender="s1", subject="sub1", date=datetime.now(), raw_body="body1", label="L1"),
        RawEmail(message_id="dup-1", sender="s1", subject="sub1", date=datetime.now(), raw_body="body1", label="L1")
    ]
    
    results = process_email_ingestion(raw_emails)
    
    assert len(results) == 1
    assert "MESSAGE_ID: dup-1" in results[0].raw_content
