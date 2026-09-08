import unittest
import os
import json
from datetime import date, datetime, timedelta
from backend.reconciliation.evidence_engine import EvidenceEngine

class TestEvidenceEngine(unittest.TestCase):
    def setUp(self):
        self.engine = EvidenceEngine()
        self.temp_report = "temp_report.json"
        self.temp_evidence = "temp_evidence.json"

    def tearDown(self):
        if os.path.exists(self.temp_report): os.remove(self.temp_report)
        if os.path.exists(self.temp_evidence): os.remove(self.temp_evidence)

    def test_exact_amount_notification_after_prime(self):
        # 1. Prime entry exists
        prime_data = {
            "records": [{
                "invoice_no": "INV-001",
                "sale_amount": 5000.0,
                "invoice_date": "2026-05-31",
                "payment_rows": [{"payment_mode": "CHEQUE", "amount": 5000.0}],
                "validation_status": "PENDING"
            }]
        }
        with open(self.temp_report, "w") as f: json.dump(prime_data, f)
        
        # 2. Bank notification arrives later
        bank_data = {
            "transactions": [{
                "transaction_id": "TXN-123",
                "amount": 5000.0,
                "transaction_date": "2026-06-01",
                "mode": "BANK",
                "utr": "UTR123"
            }]
        }
        with open(self.temp_evidence, "w") as f: json.dump(bank_data, f)
        
        # 3. Match
        self.engine.link_evidence(self.temp_report, self.temp_evidence)
        
        with open(self.temp_report, "r") as f:
            updated = json.load(f)
            rec = updated["records"][0]
            self.assertEqual(rec["validation_status"], "YELLOW_REVIEW_WITH_BANK_EVIDENCE")
            self.assertEqual(rec["bank_evidence"]["utr"], "UTR123")

    def test_notification_before_prime_should_not_match(self):
        prime_data = {
            "records": [{
                "invoice_no": "INV-002",
                "sale_amount": 1000.0,
                "invoice_date": "2026-05-31",
                "payment_rows": [{"payment_mode": "BANK", "amount": 1000.0}],
                "validation_status": "PENDING"
            }]
        }
        with open(self.temp_report, "w") as f: json.dump(prime_data, f)
        
        # Notification from 2 days ago
        bank_data = {
            "transactions": [{
                "transaction_id": "TXN-OLD",
                "amount": 1000.0,
                "transaction_date": "2026-05-29",
                "mode": "BANK",
                "utr": "OLD123"
            }]
        }
        with open(self.temp_evidence, "w") as f: json.dump(bank_data, f)
        
        self.engine.link_evidence(self.temp_report, self.temp_evidence)
        
        with open(self.temp_report, "r") as f:
            updated = json.load(f)
            self.assertEqual(updated["records"][0]["validation_status"], "PENDING")

    def test_same_amount_multiple_invoices(self):
        # Two invoices with same amount
        prime_data = {
            "records": [
                {"invoice_no": "INV-A", "sale_amount": 2000.0, "invoice_date": "2026-05-31", "payment_rows": [{"amount": 2000.0}], "validation_status": "PENDING"},
                {"invoice_no": "INV-B", "sale_amount": 2000.0, "invoice_date": "2026-05-31", "payment_rows": [{"amount": 2000.0}], "validation_status": "PENDING"}
            ]
        }
        with open(self.temp_report, "w") as f: json.dump(prime_data, f)
        
        bank_data = {
            "transactions": [{"amount": 2000.0, "transaction_date": "2026-05-31", "utr": "U1"}]
        }
        with open(self.temp_evidence, "w") as f: json.dump(bank_data, f)
        
        # Should NOT link if ambiguous
        self.engine.link_evidence(self.temp_report, self.temp_evidence)
        
        with open(self.temp_report, "r") as f:
            updated = json.load(f)
            for r in updated["records"]:
                self.assertEqual(r["validation_status"], "PENDING")

if __name__ == "__main__":
    unittest.main()
