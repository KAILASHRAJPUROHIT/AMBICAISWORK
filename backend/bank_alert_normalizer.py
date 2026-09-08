from backend.schemas import ParsedBankEmail, ParsedBankSMS, NormalizedBankAlert

def normalize_email_alert(parsed_email: ParsedBankEmail) -> NormalizedBankAlert:
    raw_content = f"Subject: {parsed_email.raw_subject}\nBody: {parsed_email.raw_body}"
    return NormalizedBankAlert(
        amount=parsed_email.amount,
        utr_reference=parsed_email.utr_reference,
        transaction_date=parsed_email.transaction_date,
        sender_bank=parsed_email.sender_bank,
        source_type="EMAIL",
        raw_content=raw_content
    )

def normalize_sms_alert(parsed_sms: ParsedBankSMS) -> NormalizedBankAlert:
    return NormalizedBankAlert(
        amount=parsed_sms.amount,
        utr_reference=parsed_sms.utr_reference,
        transaction_date=parsed_sms.transaction_date,
        sender_bank=parsed_sms.sender_bank,
        source_type="SMS",
        raw_content=parsed_sms.raw_message
    )
