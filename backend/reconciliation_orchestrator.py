from typing import List, Any, Dict
from backend.schemas import NormalizedBankAlert, AuditLogCreate, ReconciliationDecision
from backend.reconciliation_engine import reconcile_transactions
from backend.review_queue import route_review
import json

def process_bank_alert(bank_alert: NormalizedBankAlert, bills: List[Any], payments: List[Any], cheques: List[Any]) -> Dict[str, Any]:
    # Route alert into appropriate lists for the engine
    bank_alerts = []
    sms_alerts = []
    
    if bank_alert.source_type == "EMAIL":
        bank_alerts.append(bank_alert)
    elif bank_alert.source_type == "SMS":
        sms_alerts.append(bank_alert)
    else:
        # Default to bank_alerts if unknown
        bank_alerts.append(bank_alert)
        
    # 1. Reconciliation Engine
    decision: ReconciliationDecision = reconcile_transactions(
        bills=bills,
        payments=payments,
        bank_alerts=bank_alerts,
        sms_alerts=sms_alerts,
        cheques=cheques
    )
    
    # 2. Review Queue
    # Support Pydantic v2 model_dump or fallback to v1 dict
    decision_dict = decision.model_dump() if hasattr(decision, "model_dump") else decision.dict()
    review_route = route_review(decision_dict)
    
    # 3. Audit Payload Generation
    metadata = {
        "reason": decision.reason,
        "risk_flags": decision.risk_flags,
        "queue_type": review_route.get("queue_type"),
        "assigned_role": review_route.get("assigned_role")
    }
    
    audit_payload = AuditLogCreate(
        entity_type="bank_alert",
        entity_id=0, # Orchestrator generates payload; ID assigned on DB insertion
        action="process_reconciliation",
        old_status=None,
        new_status=decision.status,
        actor="system",
        metadata_json=json.dumps(metadata)
    )
    
    return {
        "decision": decision,
        "review_route": review_route,
        "audit_payload": audit_payload
    }
