import json
import os
from app.reconciliation.payment_classifier import PaymentClassifier
from app.reconciliation.matcher import Matcher
from app.reconciliation.status_engine import StatusEngine
from app.reconciliation.audit_logger import AuditLogger

class ReconciliationEngine:
    def __init__(self):
        self.classifier = PaymentClassifier()
        self.matcher = Matcher()
        self.status_engine = StatusEngine()
        self.audit_logger = AuditLogger()

    def run(self, input_file="C:/Aradhana/PrimeExports/JSON/daily_extract.json", external_sources=None):
        if not os.path.exists(input_file):
            print(f"Input file not found: {input_file}")
            return

        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        invoice = data.get("invoice", {})
        payment_rows = data.get("payment_rows", [])
        validation = data.get("validation", {})
        
        reconciliation_results = []
        
        for row in payment_rows:
            # 1. Classify
            row["payment_mode"] = self.classifier.classify(row.get("payment_mode", "UNKNOWN"))
            
            # 2. Match
            match_result = self.matcher.match(row, external_sources or [])
            
            # 3. Status
            status, reason = self.status_engine.get_status(row, match_result, validation)
            
            result_entry = {
                "row": row,
                "status": status,
                "reason": reason,
                "match_ref": match_result.get("ref") if match_result else None
            }
            reconciliation_results.append(result_entry)
            
            # 4. Audit Log
            self.audit_logger.log_event(
                invoice.get("invoice_no", "UNKNOWN"),
                "PAYMENT_RECONCILIATION",
                result_entry
            )

        final_output = {
            "invoice_no": invoice.get("invoice_no"),
            "results": reconciliation_results,
            "overall_validation": validation
        }

        output_path = "C:/Aradhana/PrimeExports/JSON/reconciliation_result.json"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=4)
            
        print(f"Reconciliation complete. Result saved to {output_path}")
        return final_output

if __name__ == "__main__":
    engine = ReconciliationEngine()
    engine.run()
