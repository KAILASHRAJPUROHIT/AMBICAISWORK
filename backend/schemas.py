from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

class ReconciliationDecision(BaseModel):
    status: str
    reason: str
    risk_flags: List[str]
    requires_human_review: bool

class AuditLogCreate(BaseModel):
    entity_type: str
    entity_id: int
    action: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    actor: str
    metadata_json: Optional[str] = None

class AuditLogResponse(AuditLogCreate):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class ParsedBankEmail(BaseModel):
    amount: Optional[float] = None
    utr_reference: Optional[str] = None
    transaction_date: Optional[str] = None
    sender_bank: Optional[str] = None
    raw_subject: str
    raw_body: str

class ParsedBankSMS(BaseModel):
    amount: Optional[float] = None
    utr_reference: Optional[str] = None
    transaction_date: Optional[str] = None
    sender_bank: Optional[str] = None
    raw_message: str

class NormalizedBankAlert(BaseModel):
    amount: Optional[float] = None
    utr_reference: Optional[str] = None
    transaction_date: Optional[str] = None
    sender_bank: Optional[str] = None
    source_type: str
    raw_content: str
