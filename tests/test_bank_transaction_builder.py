import pytest
from decimal import Decimal
from backend.schemas import NormalizedBankAlert
from backend.bank_transaction_builder import build_bank_transaction

def test_sbi_credit_alert_mapping():
    alert = NormalizedBankAlert(
        amount=5000.00,
        utr_reference="330012345678",
        transaction_date="27/10/2023",
        sender_bank="SBI",
        source_type="EMAIL",
        raw_content="MESSAGE_ID: sbi-123\nLABEL: BANK_SBI\nSubject: Alert\nBody: Your A/c XXXXXX1234 credited by Rs. 5000.00 on 27/10/2023."
    )
    
    tx = build_bank_transaction(alert)
    assert tx is not None
    assert tx.transaction_id == "sbi-123"
    assert tx.amount == Decimal("5000.00")
    assert tx.credit_or_debit == "credit"
    assert tx.bank_name == "SBI"
    assert tx.account_number == "1234"

def test_sbi_debit_alert_mapping():
    alert = NormalizedBankAlert(
        amount=1200.50,
        utr_reference="330099998888",
        transaction_date="28/10/2023",
        sender_bank="SBI",
        source_type="EMAIL",
        raw_content="MESSAGE_ID: sbi-456\nLABEL: BANK_SBI\nSubject: Alert\nBody: Your A/c XXXXXX1234 debited by Rs. 1200.50 on 28/10/2023."
    )
    
    tx = build_bank_transaction(alert)
    assert tx is not None
    assert tx.credit_or_debit == "debit"
    assert tx.amount == Decimal("1200.50")

def test_icici_settlement_mapping():
    alert = NormalizedBankAlert(
        amount=1500.50,
        utr_reference="ICICIR520231027001",
        transaction_date="27/10/2023",
        sender_bank="ICICI",
        source_type="EMAIL",
        raw_content="MESSAGE_ID: icici-789\nLABEL: BANK_ICICI\nDear Customer, transaction of INR 1,500.50 credited. UTR: ICICIR520231027001"
    )
    
    tx = build_bank_transaction(alert)
    assert tx is not None
    assert tx.credit_or_debit == "credit"
    assert tx.utr == "ICICIR520231027001"

def test_hdfc_payout_mapping():
    alert = NormalizedBankAlert(
        amount=25000.00,
        utr_reference="HDFCR520231027999",
        transaction_date="27-10-2023",
        sender_bank="HDFC",
        source_type="EMAIL",
        raw_content="MESSAGE_ID: hdfc-000\nLABEL: BANK_HDFC\nHDFC Bank: Rs 25,000.00 credited to A/c XXXXXXX1111."
    )
    
    tx = build_bank_transaction(alert)
    assert tx is not None
    assert tx.bank_name == "HDFC"
    assert tx.account_number == "1111"

def test_missing_utr_mapping():
    alert = NormalizedBankAlert(
        amount=100.00,
        utr_reference=None,
        transaction_date="27/10/2023",
        sender_bank="SBI",
        source_type="EMAIL",
        raw_content="MESSAGE_ID: msg-no-utr\nLABEL: BANK_SBI\nSmall credit of 100.00"
    )
    
    tx = build_bank_transaction(alert)
    assert tx is not None
    assert tx.utr is None

def test_malformed_alert_missing_amount():
    alert = NormalizedBankAlert(
        amount=None,
        utr_reference="UTR123",
        transaction_date="27/10/2023",
        sender_bank="SBI",
        source_type="EMAIL",
        raw_content="MESSAGE_ID: msg-no-amt\nLABEL: BANK_SBI\nNo amount here"
    )
    
    tx = build_bank_transaction(alert)
    assert tx is None

def test_malformed_alert_no_credit_debit_keywords():
    alert = NormalizedBankAlert(
        amount=500.00,
        utr_reference="UTR456",
        transaction_date="27/10/2023",
        sender_bank="SBI",
        source_type="EMAIL",
        raw_content="MESSAGE_ID: msg-ambiguous\nLABEL: BANK_SBI\nSomething happened with 500.00"
    )
    
    tx = build_bank_transaction(alert)
    assert tx is None
