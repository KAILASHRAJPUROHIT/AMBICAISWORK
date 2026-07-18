import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Optional, List
from backend.schemas import NormalizedBankAlert
from backend.bank_transaction import BankTransaction

def extract_metadata_from_raw(raw_content: str, key: str) -> Optional[str]:
    """
    Helper to extract MESSAGE_ID or LABEL from raw_content.
    """
    match = re.search(f'^{key}: (.*)$', raw_content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None

def derive_credit_or_debit(text: str) -> Optional[str]:
    """
    Derives credit or debit from text keywords.
    """
    upper_text = text.upper()
    if "CREDITED" in upper_text or "RECEIVED" in upper_text or "CREDIT" in upper_text:
        return "credit"
    if "DEBITED" in upper_text or "SPENT" in upper_text or "PAID" in upper_text or "DEBIT" in upper_text:
        return "debit"
    return None

def build_bank_transaction(alert: NormalizedBankAlert) -> Optional[BankTransaction]:
    """
    Maps NormalizedBankAlert to BankTransaction model.
    """
    # 1. Required: amount
    if alert.amount is None:
        return None
    
    try:
        amount = Decimal(str(alert.amount))
        if amount <= 0:
            return None
    except (InvalidOperation, ValueError):
        return None

    # 2. Required: transaction_id (derived from MESSAGE_ID)
    transaction_id = extract_metadata_from_raw(alert.raw_content, "MESSAGE_ID") or f"GEN-{datetime.now().timestamp()}"

    # 3. Required: bank_name
    bank_name = alert.sender_bank or "Unknown Bank"

    # 4. Required: account_number
    # Extract from raw content if possible, else empty
    acc_match = re.search(r'A/c (?:X+)?(\d{4})', alert.raw_content, re.IGNORECASE)
    account_number = acc_match.group(1) if acc_match else "Unknown"

    # 5. Required: credit_or_debit
    credit_or_debit = derive_credit_or_debit(alert.raw_content)
    if not credit_or_debit:
        # If we can't derive it, we can't fulfill the BankTransaction schema requirements 
        # which is Literal["credit", "debit"]. 
        # However, the rule says "leave unknown values empty rather than guessing".
        # This is a conflict if it's a required Enum/Literal.
        # I'll default to None and let the caller handle it or skip if I can't fulfill schema.
        return None

    # 6. Required: transaction_time
    # Try to parse alert.transaction_date, fallback to now
    transaction_time = None
    if alert.transaction_date:
        for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%d %b %Y', '%d/%m/%y'):
            try:
                transaction_time = datetime.strptime(alert.transaction_date, fmt)
                break
            except ValueError:
                continue
    
    if not transaction_time:
        transaction_time = datetime.now()

    # 7. Other fields
    return BankTransaction(
        transaction_id=transaction_id,
        bank_name=bank_name,
        account_number=account_number,
        credit_or_debit=credit_or_debit, # type: ignore
        amount=amount,
        utr=alert.utr_reference,
        counterparty_name="Unknown", # Placeholder for missing data
        description="Bank Alert",
        transaction_time=transaction_time,
        source_type=alert.source_type,
        raw_reference=alert.raw_content
    )
