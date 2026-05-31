import os
import json
import logging
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any

# Configuration
INPUT_DIR = r"C:\Aradhana\PrimeExports\ManualReports"
OUTPUT_DIR = r"C:\Aradhana\PrimeExports\JSON"
LOG_DIR = r"C:\Aradhana\PrimeExports\Logs"
JSON_OUT = os.path.join(OUTPUT_DIR, "prime_report_import.json")
FAILURES_OUT = os.path.join(OUTPUT_DIR, "prime_report_import_failures.json")
LOG_OUT = os.path.join(LOG_DIR, "prime_report_import.log")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class PrimeReportImporter:
    def __init__(self):
        self.raw_records = {} # Join Key -> Normalized Record
        # 6. Ensure folder exists
        os.makedirs(INPUT_DIR, exist_ok=True)

    def detect_report_type(self, df: pd.DataFrame) -> str:
        cols = " ".join([str(c) for c in df.columns]).upper()
        if "BOOK NAME" in cols and "VCH NO" in cols:
            return "GST_REGISTER"
        if "SALE AMT" in cols and "CASH AMT" in cols and "BANK AMT" in cols:
            return "PAYMENT_MODE_REPORT"
        if "CUST NAME" in cols and "MOB NO" in cols and "PURC AMT" in cols:
            return "TOTAL_CUSTOMER_REPORT"
        return "UNKNOWN"

    def normalize_date(self, val):
        if pd.isna(val): return None
        try:
            if isinstance(val, datetime):
                return val.strftime("%d/%m/%Y")
            return str(val)
        except: return str(val)

    def import_all(self):
        # 4 & 5. Startup logging
        print(f"SEARCH_FOLDER={INPUT_DIR}")
        
        # 2 & 3. Scan logic (non-recursive, specific extensions)
        files = [f for f in os.listdir(INPUT_DIR) if f.endswith(('.xls', '.xlsx', '.csv'))]
        
        print(f"FILES_FOUND={len(files)}")
        
        if not files:
            print("NO_MANUAL_REPORT_FILES_FOUND")
            return

        for file in files:
            path = os.path.join(INPUT_DIR, file)
            logger.info(f"Processing file: {file}")
            try:
                if file.endswith('.csv'):
                    df = pd.read_csv(path)
                else:
                    df = pd.read_excel(path)
                
                # Detect and skip garbage header rows
                header_row = 0
                for i, row in df.iterrows():
                    row_str = " ".join([str(v) for v in row.values]).upper()
                    if "VCH NO" in row_str or "CUST NAME" in row_str or "BOOK NAME" in row_str:
                        header_row = i
                        break
                
                # Reload with proper header
                if file.endswith('.csv'):
                    df = pd.read_csv(path, skiprows=header_row)
                else:
                    df = pd.read_excel(path, skiprows=header_row)

                report_type = self.detect_report_type(df)
                logger.info(f"Detected report type: {report_type}")
                
                if report_type == "GST_REGISTER":
                    self._process_gst_register(df, file)
                elif report_type == "PAYMENT_MODE_REPORT":
                    self._process_payment_mode(df, file)
                elif report_type == "TOTAL_CUSTOMER_REPORT":
                    self._process_total_customer(df, file)
                else:
                    logger.warning(f"Unknown report format in {file}")

            except Exception as e:
                logger.exception(f"Failed to parse {file}: {e}")

        # Finalize and Save
        self._finalize_and_save()

    def _get_join_key(self, row: pd.Series) -> str:
        vch = str(row.get('Vch No', '')).strip()
        if vch and vch != 'nan':
            return vch
        
        # Fallback key
        name = str(row.get('Cust Name', row.get('A/c Name', ''))).strip()
        amt = str(row.get('Sale Amt', ''))
        return f"{name}_{amt}"

    def _init_record(self, key):
        if key not in self.raw_records:
            self.raw_records[key] = {
                "invoice_no": None,
                "invoice_date": None,
                "customer_name": None,
                "mobile": None,
                "pan": None,
                "product_summary": "",
                "sale_amount": 0.0,
                "taxable_amount": 0.0,
                "cgst": 0.0,
                "sgst": 0.0,
                "cash_amount": 0.0,
                "bank_amount": 0.0,
                "card_amount": 0.0,
                "advance_amount": 0.0,
                "balance_amount": 0.0,
                "bhisi_amount": 0.0,
                "other_amount": 0.0,
                "customer_purchase_amount": 0.0,
                "payment_rows": [],
                "source_files": [],
                "validation_status": "PENDING",
                "unresolved_fields": [],
                "raw_rows": []
            }

    def _process_gst_register(self, df, filename):
        for _, row in df.iterrows():
            key = self._get_join_key(row)
            self._init_record(key)
            rec = self.raw_records[key]
            
            rec["invoice_no"] = key if not rec["invoice_no"] else rec["invoice_no"]
            rec["invoice_date"] = self.normalize_date(row.get('Date'))
            rec["customer_name"] = str(row.get('A/c Name'))
            rec["product_summary"] = str(row.get('Product Name'))
            rec["source_files"].append(filename)
            rec["raw_rows"].append(row.to_dict())

    def _process_payment_mode(self, df, filename):
        for _, row in df.iterrows():
            key = self._get_join_key(row)
            self._init_record(key)
            rec = self.raw_records[key]
            
            rec["invoice_no"] = key if not rec["invoice_no"] else rec["invoice_no"]
            rec["sale_amount"] = float(row.get('Sale Amt', 0))
            rec["cash_amount"] = float(row.get('Cash Amt', 0))
            rec["bank_amount"] = float(row.get('Bank Amt', 0))
            rec["card_amount"] = float(row.get('Card Amt', 0))
            rec["advance_amount"] = float(row.get('ADV Amt', 0))
            rec["balance_amount"] = float(row.get('BAL Amt', 0))
            rec["bhisi_amount"] = float(row.get('Bhisi Amt', 0))
            rec["other_amount"] = float(row.get('Other Amt', 0))
            
            # Map to payment rows
            modes = {
                "CASH": rec["cash_amount"],
                "BANK_UNCLASSIFIED": rec["bank_amount"],
                "CARD": rec["card_amount"],
                "ADVANCE": rec["advance_amount"],
                "BALANCE": rec["balance_amount"],
                "BHISI": rec["bhisi_amount"],
                "OTHER": rec["other_amount"]
            }
            for mode, amt in modes.items():
                if amt > 0:
                    rec["payment_rows"].append({"payment_mode": mode, "amount": amt})
            
            rec["source_files"].append(filename)
            rec["raw_rows"].append(row.to_dict())

    def _process_total_customer(self, df, filename):
        for _, row in df.iterrows():
            # Total customer report lacks Vch No, use fallback key
            key = f"{str(row.get('Cust Name')).strip()}_{str(row.get('Sale Amt', ''))}"
            self._init_record(key)
            rec = self.raw_records[key]
            
            rec["customer_name"] = str(row.get('Cust Name'))
            rec["mobile"] = str(row.get('Mob No'))
            rec["pan"] = str(row.get('PAN'))
            rec["customer_purchase_amount"] = float(row.get('Purc Amt', 0))
            
            if rec["customer_purchase_amount"] > 0:
                rec["payment_rows"].append({"payment_mode": "OLD_GOLD_EXCHANGE", "amount": rec["customer_purchase_amount"]})
            
            rec["source_files"].append(filename)
            rec["raw_rows"].append(row.to_dict())

    def _finalize_and_save(self):
        final_list = []
        for key, rec in self.raw_records.items():
            # Validation
            pay_sum = sum(p["amount"] for p in rec["payment_rows"])
            if rec["sale_amount"] > 0 and abs(pay_sum - rec["sale_amount"]) > 0.01:
                rec["validation_status"] = "NEEDS_REVIEW"
                rec["unresolved_fields"].append("PAYMENT_TOTAL_MISMATCH")
            elif not rec["invoice_no"]:
                rec["validation_status"] = "NEEDS_REVIEW"
                rec["unresolved_fields"].append("MISSING_INVOICE_NO")
            else:
                rec["validation_status"] = "GREEN"
            
            final_list.append(rec)

        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "count": len(final_list),
                "records": final_list
            }, f, indent=4)
        
        print(f"Import complete. Processed {len(final_list)} records to {JSON_OUT}")

if __name__ == "__main__":
    importer = PrimeReportImporter()
    importer.import_all()
