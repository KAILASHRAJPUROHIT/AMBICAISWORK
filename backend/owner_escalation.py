from typing import List, Dict
from datetime import datetime
from backend.schemas import OwnerEscalationRecord

_escalations_db: Dict[str, OwnerEscalationRecord] = {}

def _determine_severity(reason: str) -> str:
    reason_upper = reason.upper()
    if "LARGE AMOUNT MISMATCH" in reason_upper:
        return "CRITICAL"
    if "DUPLICATE UTR" in reason_upper:
        return "HIGH"
    if "SPLIT PAYMENT" in reason_upper or "CHEQUE RISK" in reason_upper:
        return "MEDIUM"
    return "LOW"

def create_escalation(escalation_id: str, review_id: str, escalation_reason: str) -> OwnerEscalationRecord:
    severity = _determine_severity(escalation_reason)
    
    item = OwnerEscalationRecord(
        escalation_id=escalation_id,
        review_id=review_id,
        escalation_reason=escalation_reason,
        severity=severity,
        owner_notified=False,
        created_at=datetime.utcnow().isoformat()
    )
    _escalations_db[escalation_id] = item
    return item

def resolve_escalation(escalation_id: str) -> OwnerEscalationRecord:
    if escalation_id not in _escalations_db:
        raise ValueError("Escalation not found")
        
    item = _escalations_db[escalation_id]
    if item.resolved_at is not None:
        raise ValueError("Escalation is already resolved")
        
    item.resolved_at = datetime.utcnow().isoformat()
    return item

def get_open_escalations() -> List[OwnerEscalationRecord]:
    return [e for e in _escalations_db.values() if e.resolved_at is None]

def _clear_escalations():
    # purely for test isolation
    _escalations_db.clear()
