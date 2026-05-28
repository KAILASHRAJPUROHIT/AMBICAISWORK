from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class ReviewQueueItem(BaseModel):
    entity_type: str = Field(..., description="Type of the entity to be reviewed.")
    entity_id: int = Field(..., description="ID of the entity to be reviewed.")
    current_status: str = Field(..., description="Current status of the entity.")
    proposed_status: str = Field(..., description="Proposed status for the entity.")
    risk_flags: List[str] = Field(..., description="List of risk flags associated with the entity.")
    requires_owner_escalation: bool = Field(..., description="Flag indicating if owner escalation is required.")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when the item was created.")

class ReconciliationDecision(BaseModel):
    status: str
    reason: str
    risk_flags: List[str]
    requires_human_review: bool

class RoutingResult(BaseModel):
    queue_type: Optional[str] = None
    assigned_role: Optional[str] = None
    escalation_required: bool = False
    reason: str = ""
