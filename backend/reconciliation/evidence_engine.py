import json
import os
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class EvidenceEngine:
    """Links bank notifications to existing Prime payment entries."""
    
    def __init__(self, audit_log_dir="C:/Aradhana/AuditLogs"):
        self.audit_log_dir = audit_log_dir
        os.makedirs(self.audit_log_dir, exist_ok=True)

    def link_evidence(self, report_path: str, evidence_path: str):
        """
        Scans pending Prime entries and attempts to find matching bank notifications.
        """
        if not os.path.exists(report_path) or not os.path.exists(evidence_path):
            return

        with open(report_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)
        
        with open(evidence_path, "r", encoding="utf-8") as f:
            evidence_data = json.load(f)
            # Handle list-only or dict-with-list formats
            if isinstance(evidence_data, list):
                bank_txs = evidence_data
            else:
                bank_txs = evidence_data.get("transactions", [])

        records = report_data.get("records", [])
        linked_count = 0

        for rec in records:
            # Only consider pending/unclassified items
            if rec.get("validation_status") not in ["PENDING", "NEEDS_REVIEW"]:
                continue
                
            amount = rec.get("sale_amount", 0.0)
            inv_date_str = rec.get("invoice_date")
            if not inv_date_str: continue
            
            try:
                # Prime dates are dd/mm/yyyy
                d_parts = inv_date_str.split("/")
                inv_date = date(int(d_parts[2]), int(d_parts[1]), int(d_parts[0]))
            except:
                try: inv_date = date.fromisoformat(inv_date_str)
                except: continue

            # Find matching candidates in bank notifications
            candidates = []
            for tx in bank_txs:
                if abs(tx["amount"] - amount) < 0.01:
                    # Parse bank date (could be 21/04/26 or 2026-04-21)
                    tx_date_str = tx["transaction_date"]
                    try:
                        if "/" in tx_date_str:
                             p = tx_date_str.split("/")
                             # Assume YY if 2 digits
                             yr = int(p[2])
                             if yr < 100: yr += 2000
                             tx_date = date(yr, int(p[1]), int(p[0]))
                        else:
                             tx_date = date.fromisoformat(tx_date_str)
                    except:
                        continue

                    # Rule: Notification must be on or after Prime entry
                    if tx_date >= inv_date:
                        candidates.append(tx)

            # Safety Rule: Multi-invoice same amount = Review
            if len(candidates) == 1:
                # Check if multiple invoices have this same amount
                other_matches = [r for r in records if abs(r.get("sale_amount", 0.0) - amount) < 0.01 and r != rec]
                
                if not other_matches:
                    target_tx = candidates[0]
                    rec["validation_status"] = "YELLOW_REVIEW_WITH_BANK_EVIDENCE"
                    rec["bank_evidence"] = {
                        "timestamp": datetime.now().isoformat(),
                        "bank_name": target_tx.get("label", target_tx.get("bank_name", "UNKNOWN")),
                        "amount": target_tx["amount"],
                        "utr": target_tx.get("utr") or target_tx.get("message_id"),
                        "transaction_date": target_tx["transaction_date"],
                        "source_id": target_tx.get("message_id") or target_tx.get("transaction_id"),
                        "confidence_reason": "Exact amount bank notification found after Prime entry"
                    }
                    linked_count += 1
                    
                    # Audit Log
                    self.log_audit_event("BANK_EVIDENCE_LINKED", {
                        "invoice_no": rec.get("invoice_no"),
                        "amount": amount,
                        "utr": rec["bank_evidence"]["utr"]
                    })

        if linked_count > 0:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=4)
            
        print(f"Evidence engine complete. {linked_count} potential matches found.")

    def log_audit_event(self, event_type: str, details: Dict):
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "details": details
        }
        filename = f"AUDIT_EVIDENCE_{event_type}_{datetime.now().strftime('%Y%m%d')}.json"
        path = os.path.join(self.audit_log_dir, filename)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
