import pytest
from datetime import datetime
from decimal import Decimal
from pydantic import ValidationError
from backend.bank_transaction import BankTransaction

def test_valid_credit_transaction():
    tx_data = {
        "transaction_id": "TXN123",
        "bank_name": "HDFC",
        "account_number": "123456789",
        "credit_or_debit": "credit",
        "amount": Decimal("1500.50"),
        "utr": "UTR987654",
        "counterparty_name": "John Doe",
        "description": "UPI Transfer",
        "transaction_time": datetime.now(),
        "source_type": "SMS",
        "raw_reference": "Received 1500.50 from John Doe"
    }
    tx = BankTransaction(**tx_data)
    assert tx.transaction_id == "TXN123"
    assert tx.amount == Decimal("1500.50")
    assert tx.credit_or_debit == "credit"

def test_valid_debit_transaction():
    tx_data = {
        "transaction_id": "TXN456",
        "bank_name": "ICICI",
        "account_number": "987654321",
        "credit_or_debit": "debit",
        "amount": Decimal("500.00"),
        "utr": "UTR112233",
        "counterparty_name": "Amazon",
        "description": "Shopping",
        "transaction_time": datetime.now(),
        "source_type": "Statement",
        "raw_reference": "Paid 500.00 to Amazon"
    }
    tx = BankTransaction(**tx_data)
    assert tx.transaction_id == "TXN456"
    assert tx.amount == Decimal("500.00")
    assert tx.credit_or_debit == "debit"

def test_required_field_validation():
    # Missing required field 'bank_name'
    tx_data = {
        "transaction_id": "TXN789",
        "account_number": "123456789",
        "credit_or_debit": "credit",
        "amount": Decimal("100.00"),
        "counterparty_name": "Jane Doe",
        "description": "Test",
        "transaction_time": datetime.now(),
        "source_type": "Email",
        "raw_reference": "Test ref"
    }
    with pytest.raises(ValidationError) as exc_info:
        BankTransaction(**tx_data)
    assert "bank_name" in str(exc_info.value)

def test_invalid_amount_validation():
    tx_data = {
        "transaction_id": "TXN000",
        "bank_name": "HDFC",
        "account_number": "123456789",
        "credit_or_debit": "credit",
        "amount": Decimal("-50.00"), # Invalid negative amount
        "counterparty_name": "Test",
        "description": "Test",
        "transaction_time": datetime.now(),
        "source_type": "SMS",
        "raw_reference": "Test ref"
    }
    with pytest.raises(ValidationError) as exc_info:
        BankTransaction(**tx_data)
    assert "Amount must be positive" in str(exc_info.value)

def test_zero_amount_validation():
    tx_data = {
        "transaction_id": "TXN001",
        "bank_name": "HDFC",
        "account_number": "123456789",
        "credit_or_debit": "credit",
        "amount": Decimal("0.00"), # Invalid zero amount
        "counterparty_name": "Test",
        "description": "Test",
        "transaction_time": datetime.now(),
        "source_type": "SMS",
        "raw_reference": "Test ref"
    }
    with pytest.raises(ValidationError) as exc_info:
        BankTransaction(**tx_data)
    assert "Amount must be positive" in str(exc_info.value)
