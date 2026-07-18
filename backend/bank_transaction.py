from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, Literal
from decimal import Decimal

class BankTransaction(BaseModel):
    transaction_id: str
    bank_name: str
    account_number: str
    credit_or_debit: Literal["credit", "debit"]
    amount: Decimal = Field(...)
    utr: Optional[str] = None
    counterparty_name: str
    description: str
    transaction_time: datetime
    source_type: str
    raw_reference: str

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v
