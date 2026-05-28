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

    if decision.get("current_status") == "Red":
        escalation_required = True
        reason = "Red status requires human review"

    if "duplicate_utr" in decision.get("risk_flags", []):
        escalation_required = True
        reason = "Duplicate UTR requires owner escalation"

    if "large_amount_mismatch" in decision.get("risk_flags", []):
        escalation_required = True
        reason = "Large amount mismatch requires owner escalation"

    if "split_payment" in decision.get("risk_flags", []):
        assigned_role = "accountant"
        reason = "Split payments require accountant review"

    if decision.get("current_status") == "Yellow":
        assigned_role = "accountant"
        reason = "Yellow status requires accountant review"

    if decision.get("current_status") == "Orange":
        queue_type = "approval"
        assigned_role = "approver"
        reason = "Orange status requires approval workflow"

    if decision.get("current_status") == "Blue":
        queue_type = "pending"
        assigned_role = "none"
        reason = "Blue remains pending until cheque cleared"

    return {
        "queue_type": queue_type,
        "assigned_role": assigned_role,
        "escalation_required": escalation_required,
        "reason": reason
    }
