from typing import List, Dict
from datetime import datetime
from backend.schemas import ManagedReviewItem

_reviews_db: Dict[str, ManagedReviewItem] = {}

def create_review_item(
    review_id: str,
    entity_type: str,
    entity_id: str,
    queue_type: str,
    assigned_role: str,
    escalation_required: bool,
    reason: str
) -> ManagedReviewItem:
    item = ManagedReviewItem(
        review_id=review_id,
        entity_type=entity_type,
        entity_id=entity_id,
        queue_type=queue_type,
        assigned_role=assigned_role,
        escalation_required=escalation_required,
        status="OPEN",
        reason=reason,
        created_at=datetime.utcnow().isoformat()
    )
    _reviews_db[review_id] = item
    return item

def assign_review(review_id: str, new_role: str) -> ManagedReviewItem:
    if review_id not in _reviews_db:
        raise ValueError("Review not found")
    
    item = _reviews_db[review_id]
    if item.status != "OPEN":
        raise ValueError(f"Invalid transition from {item.status} to IN_REVIEW")
    
    item.status = "IN_REVIEW"
    item.assigned_role = new_role
    return item

def resolve_review(review_id: str) -> ManagedReviewItem:
    if review_id not in _reviews_db:
        raise ValueError("Review not found")
        
    item = _reviews_db[review_id]
    if item.status != "IN_REVIEW":
        raise ValueError(f"Invalid transition from {item.status} to RESOLVED")
        
    item.status = "RESOLVED"
    item.resolved_at = datetime.utcnow().isoformat()
    return item

def escalate_review(review_id: str) -> ManagedReviewItem:
    if review_id not in _reviews_db:
        raise ValueError("Review not found")
        
    item = _reviews_db[review_id]
    if item.status != "OPEN":
        raise ValueError(f"Invalid transition from {item.status} to ESCALATED")
        
    item.status = "ESCALATED"
    item.escalation_required = True
    return item

def get_open_reviews() -> List[ManagedReviewItem]:
    return [r for r in _reviews_db.values() if r.status == "OPEN"]

def _clear_queue():
    # purely for test isolation
    _reviews_db.clear()
