from datetime import datetime
from pydantic import BaseModel, Field

class ReviewQueueItem(BaseModel):
    entity_type: str = Field(..., description="Type of the entity to be reviewed.")
    entity_id: int = Field(..., description="ID of the entity to be reviewed.")
    current_status: str = Field(..., description="Current status of the entity.")
    proposed_status: str = Field(..., description="Proposed status for the entity.")
    risk_flags: List[str] = Field(..., description="List of risk flags associated with the entity.")
    requires_owner_escalation: bool = Field(..., description="Flag indicating if owner escalation is required.")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when the item was created.")

def route_review(decision: dict) -> dict:
    queue_type = None
    assigned_role = None
    escalation_required = False
    reason = ""

    if decision["status"] == "Red":
        queue_type = "HumanReview"
        assigned_role = "Accountant"
        escalation_required = True
        reason = "Red always requires human review."
    elif decision["risk_flags"]:
        if "Duplicate UTR" in decision["risk_flags"]:
            queue_type = "OwnerEscalation"
            assigned_role = "Owner"
            escalation_required = True
            reason = "Duplicate UTR requires owner escalation."
        elif any(flag.startswith("Large amount mismatch") for flag in decision["risk_flags"]):
            queue_type = "OwnerEscalation"
            assigned_role = "Owner"
            escalation_required = True
            reason = "Large amount mismatch requires owner escalation."
    elif decision["status"] == "Split Payment":
        queue_type = "AccountantReview"
        assigned_role = "Accountant"
        escalation_required = False
        reason = "Split payments require accountant review."
    elif decision["status"] == "Yellow":
        queue_type = "AccountantReview"
        assigned_role = "Accountant"
        escalation_required = False
        reason = "Yellow requires accountant review."
    elif decision["status"] == "Orange":
        queue_type = "ApprovalWorkflow"
        assigned_role = "Approver"
        escalation_required = False
        reason = "Orange requires approval workflow."
    elif decision["status"] == "Blue":
        queue_type = "PendingChequeClearance"
        assigned_role = "Accountant"
        escalation_required = False
        reason = "Blue remains pending until cheque cleared."

    return {
        "queue_type": queue_type,
        "assigned_role": assigned_role,
        "escalation_required": escalation_required,
        "reason": reason
    }
