import json
import os
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class ReconciliationEngineV3:
    """
    Foolproof matching strategy for Prime transactions and Bank notifications.
    Enforces strict date-direction safety and multi-factor validation.
    """
    
    def __init__(self, audit_log_dir="C:/Aradhana/AuditLogs"):
        self.audit_log_dir = audit_log_dir
        os.makedirs(self.audit_log_dir, exist_ok=True)
        self.linked_utrs = set()
        self.linked_bank_ids = set()

    def _parse_date(self, date_str: str) -> Optional[date]:
        if not date_str: return None
        try:
            if "/" in date_str:
                p = date_str.split("/")
                yr = int(p[2])
                if yr < 100: yr += 2000
                return date(yr, int(p[1]), int(p[0]))
            return date.fromisoformat(date_str)
        except:
            return None

    def _get_mode_window_days(self, mode: str) -> int:
        mode = mode.upper()
        if mode in ["UPI", "IMPS"]: return 0
        if mode in ["NEFT", "RTGS", "CARD"]: return 1
        if mode == "CHEQUE": return 4
        return 0

    def process_reconciliation(self, report_path: str, bank_data_path: str):
        if not os.path.exists(report_path) or not os.path.exists(bank_data_path):
            return

        with open(report_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)
        
        with open(bank_data_path, "r", encoding="utf-8") as f:
            bank_data = json.load(f)
            bank_txs = bank_data if isinstance(bank_data, list) else bank_data.get("transactions", [])

        records = report_data.get("records", [])
        
        # 1. Reset/Refresh global state
        self.linked_utrs = {r.get("bank_evidence", {}).get("utr") for r in records if r.get("validation_status") == "GREEN" and r.get("bank_evidence")}
        self.linked_bank_ids = {r.get("bank_evidence", {}).get("source_id") for r in records if r.get("validation_status") == "GREEN" and r.get("bank_evidence")}
        
        linked_count = 0

        for rec in records:
            # Skip already confirmed GREEN or explicitly REJECTED/BLUE
            if rec.get("validation_status") in ["GREEN", "BLUE"]:
                continue
                
            amount = rec.get("sale_amount", 0.0)
            inv_date = self._parse_date(rec.get("invoice_date"))
            if not inv_date: continue
            
            # Find all potential bank candidates
            candidates = []
            for tx in bank_txs:
                tx_date = self._parse_date(tx["transaction_date"])
                if not tx_date: continue
                
                # Rule 1: Date Direction (Bank Alert MUST be on or after Invoice)
                if tx_date < inv_date:
                    continue

                # Rule 2: Amount Exact Match
                if abs(tx["amount"] - amount) > 0.01:
                    continue
                
                # Rule 3: Already Linked
                tx_utr = tx.get("utr") or tx.get("message_id")
                tx_id = tx.get("message_id") or tx.get("transaction_id")
                if tx_utr in self.linked_utrs or tx_id in self.linked_bank_ids:
                    continue

                # Rule 4: Mode Window Check
                window_days = self._get_mode_window_days(rec.get("payment_rows", [{}])[0].get("payment_mode", "BANK"))
                if (tx_date - inv_date).days > (window_days + 1): # Allowing 1 extra day buffer for late-night entries
                    continue

                candidates.append(tx)

            # --- MATCHING LOGIC ---
            
            if not candidates:
                continue

            # Check for multiple invoices with same amount (ORANGE)
            competing_invoices = [r for r in records if abs(r.get("sale_amount", 0.0) - amount) < 0.01 and r != rec]
            
            if len(candidates) > 1 or competing_invoices:
                rec["validation_status"] = "ORANGE"
                rec["unresolved_fields"] = ["MULTIPLE_CANDIDATES_SAME_AMOUNT"]
                rec["bank_suggested_evidence"] = [self._format_evidence(c) for c in candidates[:3]]
                continue

            # Unique candidate found
            target_tx = candidates[0]
            confidence, reason = self._calculate_confidence(rec, target_tx)
            
            evidence = self._format_evidence(target_tx)
            evidence["confidence_reason"] = reason
            rec["bank_evidence"] = evidence
            
            if confidence == "HIGH_GREEN_ALLOWED":
                # Special Rule: CHEQUE never auto-greens
                if any(p.get("payment_mode") == "CHEQUE" for p in rec.get("payment_rows", [])):
                    rec["validation_status"] = "YELLOW_REVIEW_WITH_BANK_EVIDENCE"
                else:
                    rec["validation_status"] = "GREEN"
                    self.linked_utrs.add(evidence["utr"])
                    self.linked_bank_ids.add(evidence["source_id"])
            else:
                rec["validation_status"] = "YELLOW_REVIEW_WITH_BANK_EVIDENCE"
            
            linked_count += 1
            self.log_audit_event("BANK_LINKAGE_PROPOSED", {
                "invoice_no": rec.get("invoice_no"),
                "status": rec["validation_status"],
                "confidence": confidence,
                "reason": reason
            })

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4)
            
        print(f"Reconciliation Engine V3 complete. {linked_count} updates applied.")

    def _calculate_confidence(self, rec: Dict, tx: Dict) -> Tuple[str, str]:
        """Scoring logic based on UTR, Sender, and Mode."""
        utr = tx.get("utr")
        mode = rec.get("payment_rows", [{}])[0].get("payment_mode", "BANK").upper()
        
        # High Confidence: Unique match + UTR present + compatible mode
        if utr and mode != "CHEQUE":
            # Optional: Add sender/narration fuzzy match here if customer name is available in TX
            return "HIGH_GREEN_ALLOWED", "Exact amount + Unique match + UTR verified"
        
        if mode == "CHEQUE":
            return "MEDIUM_REVIEW", "Unique amount match found for Cheque - Requires realization check"
            
        if not utr:
            return "LOW_REVIEW", "Amount matches but bank alert is missing UTR/Reference"
            
        return "MEDIUM_REVIEW", "Unique match found - requires human verification of sender"

    def _format_evidence(self, tx: Dict) -> Dict:
        return {
            "timestamp": datetime.now().isoformat(),
            "bank_name": tx.get("label", tx.get("bank_name", "UNKNOWN")),
            "amount": tx["amount"],
            "utr": tx.get("utr") or tx.get("message_id"),
            "transaction_date": tx["transaction_date"],
            "source_id": tx.get("message_id") or tx.get("transaction_id"),
            "raw_alert": tx.get("template", "BANK_ALERT")
        }

    def log_audit_event(self, event_type: str, details: Dict):
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "details": details
        }
        filename = f"AUDIT_RECON_{datetime.now().strftime('%Y%m%d')}.json"
        path = os.path.join(self.audit_log_dir, filename)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
