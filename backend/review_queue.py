from datetime import datetime
from typing import List

class ReviewQueueItem:
    def __init__(self, entity_type: str, entity_id: int, current_status: str, proposed_status: str, risk_flags: List[str], requires_owner_escalation: bool, created_at: datetime):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.current_status = current_status
        self.proposed_status = proposed_status
        self.risk_flags = risk_flags
        self.requires_owner_escalation = requires_owner_escalation
        self.created_at = created_at

def route_review(decision: dict) -> dict:
    queue_type = "default"
    assigned_role = "accountant"
    escalation_required = False
    reason = ""

    flags = decision.get("risk_flags", [])
    status = decision.get("status")

    if "Duplicate UTR" in flags:
        queue_type = "OwnerEscalation"
        assigned_role = "Owner"
        escalation_required = True
        reason = "Duplicate UTR requires owner escalation."
    elif status == "Red":
        queue_type = "HumanReview"
        assigned_role = "Accountant"
        escalation_required = True
        reason = "Red always requires human review."
    elif status == "Orange":
        queue_type = "ApprovalWorkflow"
        assigned_role = "Approver"
        escalation_required = False
        reason = "Orange requires approval workflow."
    elif "Split Payment" in flags:
        queue_type = "AccountantReview"
        assigned_role = "Accountant"
        escalation_required = False
        reason = "Split payments require accountant review."
    elif status == "Yellow":
        queue_type = "AccountantReview"
        assigned_role = "Accountant"
        escalation_required = False
        reason = "Yellow requires accountant review."

    return {
        "queue_type": queue_type,
        "assigned_role": assigned_role,
        "escalation_required": escalation_required,
        "reason": reason
    }
