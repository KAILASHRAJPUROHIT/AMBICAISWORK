import pytest
from backend.review_queue_manager import (
    create_review_item,
    assign_review,
    resolve_review,
    escalate_review,
    get_open_reviews,
    _clear_queue
)

@pytest.fixture(autouse=True)
def clean_queue():
    _clear_queue()
    yield

def test_create_review_item():
    item = create_review_item(
        review_id="REV-1",
        entity_type="bank_alert",
        entity_id="100",
        queue_type="AccountantReview",
        assigned_role="Accountant",
        escalation_required=False,
        reason="Needs manual verification"
    )
    assert item.review_id == "REV-1"
    assert item.status == "OPEN"

def test_assign_review():
    create_review_item("REV-1", "bill", "20", "default", "Accountant", False, "test")
    item = assign_review("REV-1", "SeniorAccountant")
    assert item.status == "IN_REVIEW"
    assert item.assigned_role == "SeniorAccountant"

def test_resolve_review():
    create_review_item("REV-1", "bill", "20", "default", "Accountant", False, "test")
    assign_review("REV-1", "Accountant")
    item = resolve_review("REV-1")
    assert item.status == "RESOLVED"
    assert item.resolved_at is not None

def test_escalation_path():
    create_review_item("REV-1", "bill", "20", "default", "Accountant", False, "test")
    item = escalate_review("REV-1")
    assert item.status == "ESCALATED"
    assert item.escalation_required is True

def test_open_review_filtering():
    create_review_item("REV-1", "bill", "1", "default", "Accountant", False, "test")
    create_review_item("REV-2", "bill", "2", "default", "Accountant", False, "test")
    
    assign_review("REV-1", "Accountant")
    
    open_items = get_open_reviews()
    assert len(open_items) == 1
    assert open_items[0].review_id == "REV-2"

def test_status_transition_validation():
    create_review_item("REV-1", "bill", "20", "default", "Accountant", False, "test")
    
    # Cannot resolve from OPEN
    with pytest.raises(ValueError, match="Invalid transition"):
        resolve_review("REV-1")
        
    assign_review("REV-1", "Accountant")
    
    # Cannot escalate from IN_REVIEW
    with pytest.raises(ValueError, match="Invalid transition"):
        escalate_review("REV-1")
        
    resolve_review("REV-1")
    
    # Cannot assign from RESOLVED
    with pytest.raises(ValueError, match="Invalid transition"):
        assign_review("REV-1", "Admin")
