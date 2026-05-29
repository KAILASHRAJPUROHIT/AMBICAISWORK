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
