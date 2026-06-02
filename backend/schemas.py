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
    account_suffix: Optional[str] = None
    payer_name: Optional[str] = None
    confidence: str = "LOW"

class NormalizedBankAlert(BaseModel):
    amount: Optional[float] = None
    utr_reference: Optional[str] = None
    transaction_date: Optional[str] = None
    sender_bank: Optional[str] = None
    source_type: str
    raw_content: str

class ManagedReviewItem(BaseModel):
    review_id: str
    entity_type: str
    entity_id: str
    queue_type: str
    assigned_role: str
    escalation_required: bool
    status: str
    reason: str
    created_at: str
    resolved_at: Optional[str] = None

class OwnerEscalationRecord(BaseModel):
    escalation_id: str
    review_id: str
    escalation_reason: str
    severity: str
    owner_notified: bool
    created_at: str
    resolved_at: Optional[str] = None

class DailySummary(BaseModel):
    generated_at: str
    processed_count: int
    open_reviews: int
    escalated_reviews: int
    resolved_reviews: int
    high_risk_count: int
    critical_risk_count: int
    summary_notes: str

# Appended from backend/review_schemas.py
class ReviewQueueItem(BaseModel):
    entity_type: str = Field(..., description="Type of the entity (e.g., Bill, Payment)")
    entity_id: int = Field(..., description="ID of the entity")
    current_status: str = Field(..., description="Current status of the entity")
    proposed_status: str = Field(..., description="Proposed status of the entity")
    risk_flags: List[str] = Field([], description="List of risk flags associated with the entity")
    requires_owner_escalation: bool = Field(False, description="Indicates if owner escalation is required")
    created_at: datetime = Field(datetime.now(), description="Timestamp when the review item was created")

class RoutingResult(BaseModel):
    queue_type: str = Field(..., description="Type of the queue (e.g., default, approval, pending)")
    assigned_role: str = Field(..., description="Role assigned to handle the review")
    escalation_required: bool = Field(..., description="Indicates if escalation is required")
    reason: str = Field(..., description="Reason for the routing decision")

class RawEmail(BaseModel):
    message_id: str
    sender: str
    subject: str
    date: datetime
    raw_body: str
    label: str
