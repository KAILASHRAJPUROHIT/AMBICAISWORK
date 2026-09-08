from typing import List
from backend.schemas import RawEmail, NormalizedBankAlert
from backend.email_parser import parse_bank_email
from backend.bank_alert_normalizer import normalize_email_alert

def process_email_ingestion(emails: List[RawEmail]) -> List[NormalizedBankAlert]:
    """
    Processes a list of RawEmail objects through the parsing and normalization pipeline.
    Preserves source label and raw message_id in the resulting NormalizedBankAlert.
    Prevents duplicates within the input list using message_id.
    """
    normalized_alerts: List[NormalizedBankAlert] = []
    seen_message_ids = set()

    for email in emails:
        # Prevent duplicates based on message_id
        if email.message_id in seen_message_ids:
            continue
        
        # 1. Parse raw email content
        parsed_email = parse_bank_email(email.subject, email.raw_body)
        
        # 2. Normalize parsed email
        normalized_alert = normalize_email_alert(parsed_email)
        
        # 3. Add session-specific metadata
        # We need to make sure NormalizedBankAlert schema supports or we just use it as is.
        # According to schemas.py: NormalizedBankAlert has amount, utr_reference, transaction_date, 
        # sender_bank, source_type, raw_content.
        
        # Since I cannot modify the schema, I will ensure the raw_content includes the message_id and label 
        # if not already present or just return the standard normalized alert.
        # Actually, the requirement says "preserve source label" and "preserve raw message_id".
        # If the schema doesn't have these fields, I might need to append them to raw_content.
        
        # Let's check schemas.py again to see if I should add fields or if they are already there.
        # I'll proceed with what's available and use raw_content for preservation if needed.
        
        normalized_alert.raw_content = f"MESSAGE_ID: {email.message_id}\nLABEL: {email.label}\n{normalized_alert.raw_content}"
        
        normalized_alerts.append(normalized_alert)
        seen_message_ids.add(email.message_id)

    return normalized_alerts
