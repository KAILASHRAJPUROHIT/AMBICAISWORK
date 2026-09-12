from typing import Optional
from pydantic import BaseModel


class ParsedBankSMS(BaseModel):
    amount: Optional[float] = None
    utr_reference: Optional[str] = None
    transaction_date: Optional[str] = None
    sender_bank: Optional[str] = None
    raw_message: str
    account_suffix: Optional[str] = None
    payer_name: Optional[str] = None
    confidence: str = "LOW"
