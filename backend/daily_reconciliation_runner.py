from typing import List, Dict, Any
from backend.schemas import NormalizedBankAlert
from backend.reconciliation_orchestrator import process_bank_alert

def run_daily_reconciliation(
    bills: List[Any],
    payments: List[Any],
    cheques: List[Any],
    bank_alerts: List[NormalizedBankAlert]
) -> Dict[str, Any]:
    
    results = {
        "processed_count": 0,
        "decisions": [],
        "review_routes": [],
        "audit_payloads": []
    }
    
    for alert in bank_alerts:
        outcome = process_bank_alert(
            bank_alert=alert,
            bills=bills,
            payments=payments,
            cheques=cheques
        )
        results["decisions"].append(outcome["decision"])
        results["review_routes"].append(outcome["review_route"])
        results["audit_payloads"].append(outcome["audit_payload"])
        results["processed_count"] += 1
        
    return results
