from backend.review_queue import route_review

def test_duplicate_utr():
    decision = {
        "current_status": "Yellow",
        "risk_flags": ["duplicate_utr"]
    }
    result = route_review(decision)
    assert result["queue_type"] == "default"
    assert result["assigned_role"] == "accountant"
    assert result["escalation_required"] is True
    assert result["reason"] == "Duplicate UTR requires owner escalation"

def test_bounced_cheque():
    decision = {
        "current_status": "Red",
        "risk_flags": ["bounced_cheque"]
    }
    result = route_review(decision)
    assert result["queue_type"] == "default"
    assert result["assigned_role"] == "none"
    assert result["escalation_required"] is True
    assert result["reason"] == "Red status requires human review"

def test_delayed_neft():
    decision = {
        "current_status": "Orange",
        "risk_flags": ["delayed_neft"]
    }
    result = route_review(decision)
    assert result["queue_type"] == "approval"
    assert result["assigned_role"] == "approver"
    assert result["escalation_required"] is False
    assert result["reason"] == "Orange status requires approval workflow"

def test_split_payment():
    decision = {
        "current_status": "Yellow",
        "risk_flags": ["split_payment"]
    }
    result = route_review(decision)
    assert result["queue_type"] == "default"
    assert result["assigned_role"] == "accountant"
    assert result["escalation_required"] is False
    assert result["reason"] == "Split payments require accountant review"

def test_yellow():
    decision = {
        "current_status": "Yellow",
        "risk_flags": []
    }
    result = route_review(decision)
    assert result["queue_type"] == "default"
    assert result["assigned_role"] == "accountant"
    assert result["escalation_required"] is False
    assert result["reason"] == "Yellow status requires accountant review"
