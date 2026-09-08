import pytest
from backend.owner_escalation import (
    create_escalation,
    resolve_escalation,
    get_open_escalations,
    _clear_escalations
)

@pytest.fixture(autouse=True)
def clean_db():
    _clear_escalations()
    yield

def test_create_escalation():
    esc = create_escalation("ESC-1", "REV-100", "Needs review")
    assert esc.escalation_id == "ESC-1"
    assert esc.review_id == "REV-100"
    assert esc.severity == "LOW" # default fallback
    assert esc.owner_notified is False
    assert esc.resolved_at is None

def test_resolve_escalation():
    create_escalation("ESC-1", "REV-100", "Duplicate UTR")
    esc = resolve_escalation("ESC-1")
    assert esc.resolved_at is not None

def test_open_escalation_filtering():
    create_escalation("ESC-1", "REV-1", "Reason A")
    create_escalation("ESC-2", "REV-2", "Reason B")
    
    resolve_escalation("ESC-1")
    
    open_escs = get_open_escalations()
    assert len(open_escs) == 1
    assert open_escs[0].escalation_id == "ESC-2"

def test_severity_assignment():
    # Duplicate UTR → HIGH
    esc_dup = create_escalation("E1", "R1", "Contains a Duplicate UTR error")
    assert esc_dup.severity == "HIGH"
    
    # Large Amount Mismatch → CRITICAL
    esc_large = create_escalation("E2", "R2", "A Large Amount Mismatch detected")
    assert esc_large.severity == "CRITICAL"
    
    # Split Payment → MEDIUM
    esc_split = create_escalation("E3", "R3", "Split Payment identified")
    assert esc_split.severity == "MEDIUM"
    
    # Cheque Risk → MEDIUM
    esc_cheque = create_escalation("E4", "R4", "Cheque Risk potential")
    assert esc_cheque.severity == "MEDIUM"

def test_invalid_resolution_handling():
    # Resolving non-existent
    with pytest.raises(ValueError, match="Escalation not found"):
        resolve_escalation("ESC-999")
        
    create_escalation("ESC-1", "REV-1", "Reason")
    resolve_escalation("ESC-1")
    
    # Resolving already resolved
    with pytest.raises(ValueError, match="Escalation is already resolved"):
        resolve_escalation("ESC-1")
