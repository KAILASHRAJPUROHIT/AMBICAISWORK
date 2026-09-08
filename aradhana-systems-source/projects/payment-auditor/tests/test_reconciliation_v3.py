import unittest
import os
import json
from datetime import date, datetime, timedelta
from backend.reconciliation.reconciliation_engine_v3 import ReconciliationEngineV3

class TestReconciliationEngineV3(unittest.TestCase):
    def setUp(self):
        self.engine = ReconciliationEngineV3()
        self.temp_report = "temp_report_v3.json"
        self.temp_bank = "temp_bank_v3.json"

    def tearDown(self):
        if os.path.exists(self.temp_report): os.remove(self.temp_report)
        if os.path.exists(self.temp_bank): os.remove(self.temp_bank)

    def test_older_alert_must_not_match(self):
        # Invoice on May 31
        prime_data = {
            "records": [{
                "invoice_no": "INV-NEW",
                "sale_amount": 5000.0,
                "invoice_date": "31/05/2026",
                "payment_rows": [{"payment_mode": "BANK", "amount": 5000.0}],
                "validation_status": "PENDING"
            }]
        }
        with open(self.temp_report, "w") as f: json.dump(prime_data, f)
        
        # Alert from May 29 (Older)
        bank_data = [{
            "transaction_id": "TXN-OLD",
            "amount": 5000.0,
            "transaction_date": "2026-05-29",
            "utr": "UTR_OLD"
        }]
        with open(self.temp_bank, "w") as f: json.dump(bank_data, f)
        
        self.engine.process_reconciliation(self.temp_report, self.temp_bank)
        
        with open(self.temp_report, "r") as f:
            updated = json.load(f)
            self.assertEqual(updated["records"][0]["validation_status"], "PENDING", "Older alert should be ignored")

    def test_duplicate_same_amount_invoices_go_orange(self):
        prime_data = {
            "records": [
                {"invoice_no": "INV-A", "sale_amount": 2000.0, "invoice_date": "31/05/2026", "payment_rows": [{"amount": 2000.0}], "validation_status": "PENDING"},
                {"invoice_no": "INV-B", "sale_amount": 2000.0, "invoice_date": "31/05/2026", "payment_rows": [{"amount": 2000.0}], "validation_status": "PENDING"}
            ]
        }
        with open(self.temp_report, "w") as f: json.dump(prime_data, f)
        
        bank_data = [{"amount": 2000.0, "transaction_date": "2026-05-31", "utr": "U1"}]
        with open(self.temp_bank, "w") as f: json.dump(bank_data, f)
        
        self.engine.process_reconciliation(self.temp_report, self.temp_bank)
        
        with open(self.temp_report, "r") as f:
            updated = json.load(f)
            self.assertEqual(updated["records"][0]["validation_status"], "ORANGE")
            self.assertIn("MULTIPLE_CANDIDATES_SAME_AMOUNT", updated["records"][0]["unresolved_fields"])

    def test_cheque_never_auto_green(self):
        prime_data = {
            "records": [{
                "invoice_no": "CHQ-101",
                "sale_amount": 7500.0,
                "invoice_date": "31/05/2026",
                "payment_rows": [{"payment_mode": "CHEQUE", "amount": 7500.0}],
                "validation_status": "PENDING"
            }]
        }
        with open(self.temp_report, "w") as f: json.dump(prime_data, f)
        
        bank_data = [{"amount": 7500.0, "transaction_date": "2026-06-02", "utr": "CHQ_CLEAR"}]
        with open(self.temp_bank, "w") as f: json.dump(bank_data, f)
        
        self.engine.process_reconciliation(self.temp_report, self.temp_bank)
        
        with open(self.temp_report, "r") as f:
            updated = json.load(f)
            # Should be YELLOW_REVIEW even with unique UTR match
            self.assertEqual(updated["records"][0]["validation_status"], "YELLOW_REVIEW_WITH_BANK_EVIDENCE")

    def test_high_confidence_green(self):
        prime_data = {
            "records": [{
                "invoice_no": "VALID-123",
                "sale_amount": 1250.0,
                "invoice_date": "31/05/2026",
                "payment_rows": [{"payment_mode": "UPI", "amount": 1250.0}],
                "validation_status": "PENDING"
            }]
        }
        with open(self.temp_report, "w") as f: json.dump(prime_data, f)
        
        bank_data = [{"amount": 1250.0, "transaction_date": "2026-05-31", "utr": "UPI_REF_999"}]
        with open(self.temp_bank, "w") as f: json.dump(bank_data, f)
        
        self.engine.process_reconciliation(self.temp_report, self.temp_bank)
        
        with open(self.temp_report, "r") as f:
            updated = json.load(f)
            self.assertEqual(updated["records"][0]["validation_status"], "GREEN")

if __name__ == "__main__":
    unittest.main()
