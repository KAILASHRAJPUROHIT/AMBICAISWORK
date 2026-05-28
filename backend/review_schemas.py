from pydantic import BaseModel, Field
from datetime import datetime

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
