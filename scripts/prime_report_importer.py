import os
import json
import logging
import pandas as pd
import io
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# Configuration
INPUT_DIR = r"C:\Aradhana\PrimeExports\ManualReports"
OUTPUT_DIR = r"C:\Aradhana\PrimeExports\JSON"
LOG_DIR = r"C:\Aradhana\PrimeExports\Logs"
JSON_OUT = os.path.join(OUTPUT_DIR, "prime_report_import.json")
FAILURES_OUT = os.path.join(OUTPUT_DIR, "prime_report_import_failures.json")
LOG_OUT = os.path.join(LOG_DIR, "prime_report_import.log")
DEBUG_LOG = os.path.join(LOG_DIR, "prime_report_import_debug.log")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Setup Main Logger
logging.basicConfig(filename=LOG_OUT, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Setup Debug Logger
debug_logger = logging.getLogger("debug")
debug_handler = logging.FileHandler(DEBUG_LOG, mode='w', encoding='utf-8')
debug_handler.setFormatter(logging.Formatter("%(message)s"))
debug_logger.addHandler(debug_handler)
debug_logger.setLevel(logging.DEBUG)

class PrimeReportImporter:
    def __init__(self):
        self.raw_records = {} # Join Key -> Normalized Record
        self.failures = []
        os.makedirs(INPUT_DIR, exist_ok=True)

    def log_debug(self, msg: str):
        debug_logger.debug(msg)

    def detect_report_type(self, df: pd.DataFrame) -> str:
        cols = " ".join([str(c) for c in df.columns]).upper()
        if "BOOK NAME" in cols and "VCH NO" in cols:
            return "GST_REGISTER"
        if "SALE AMT" in cols and "CASH AMT" in cols and "BANK AMT" in cols:
            return "PAYMENT_MODE_REPORT"
        if "CUST NAME" in cols and "MOB NO" in cols and "PURC AMT" in cols:
            return "TOTAL_CUSTOMER_REPORT"
        
        # Also check first few rows for keywords if columns are generic
        sample_text = ""
        if not df.empty:
            sample_text = " ".join(df.iloc[:5].astype(str).values.flatten()).upper()
        
        if "VCH NO" in sample_text and "BOOK NAME" in sample_text:
            return "GST_REGISTER"
        if "CASH AMT" in sample_text and "SALE AMT" in sample_text:
            return "PAYMENT_MODE_REPORT"
        if "MOB NO" in sample_text and "PURC AMT" in sample_text:
            return "TOTAL_CUSTOMER_REPORT"
            
        return "UNKNOWN"

    def normalize_date(self, val):
        if pd.isna(val) or val == 'None' or val == '': return None
        try:
            if isinstance(val, datetime):
                return val.strftime("%d/%m/%Y")
            # Try to parse strings like '2026-05-31 00:00:00'
            return pd.to_datetime(val).strftime("%d/%m/%Y")
        except: return str(val)

    def try_parse_as_text(self, path: str) -> Optional[pd.DataFrame]:
        """
        Attempts to read a file as text and parse it.
        Supports: CSV, TSV (Tab), and multiple-space delimited.
        """
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [f.readline() for _ in range(100)]
            
            content = "".join(lines)
            
            # Detect delimiter
            if '\t' in content:
                delim = '\t'
            elif ',' in content:
                delim = ','
            else:
                delim = r'\s{2,}' # Regex for 2 or more spaces
            
            # Find the header row
            header_row_idx = -1
            keywords = ["VCH NO", "BOOK NAME", "CUST NAME", "SALE AMT", "MOB NO"]
            for i, line in enumerate(lines):
                if any(kw in line.upper() for kw in keywords):
                    header_row_idx = i
                    break
            
            if header_row_idx == -1:
                return None

            # Read the file
            df = pd.read_csv(path, sep=delim, skiprows=header_row_idx, engine='python', on_bad_lines='skip')
            return df
        except Exception as e:
            self.log_debug(f"Text parse attempt failed for {os.path.basename(path)}: {e}")
            return None

    def import_all(self):
        print(f"SEARCH_FOLDER={INPUT_DIR}")
        files = [f for f in os.listdir(INPUT_DIR) if f.endswith(('.xls', '.xlsx', '.csv', '.txt'))]
        print(f"FILES_FOUND={len(files)}")
        
        if not files:
            print("NO_MANUAL_REPORT_FILES_FOUND")
            return

        for file in files:
            path = os.path.join(INPUT_DIR, file)
            self.log_debug(f"\nFILE: {file}")
            self.log_debug(f"EXTENSION: {os.path.splitext(file)[1]}")
            
            # Log first 20 lines for diagnosis
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    first_20 = [f.readline().strip() for _ in range(20)]
                self.log_debug("FIRST 20 LINES:")
                for line in first_20:
                    self.log_debug(f"  {line}")
            except Exception as e:
                self.log_debug(f"Could not read lines for debug: {e}")

            df = None
            # Attempt Excel first for xls/xlsx
            if file.endswith(('.xls', '.xlsx')):
                try:
                    df = pd.read_excel(path)
                    self.log_debug("Parsed successfully with Excel engine.")
                except Exception as e:
                    self.log_debug(f"Excel engine failed: {e}. Attempting text fallback...")
            
            # Fallback to text parser if excel failed or it's a csv/txt
            if df is None:
                df = self.try_parse_as_text(path)
                if df is not None:
                    self.log_debug("Parsed successfully with Text fallback.")

            if df is not None:
                # Find real headers if first row was garbage
                keywords = ["VCH NO", "BOOK NAME", "CUST NAME", "SALE AMT", "MOB NO", "DATE"]
                header_row = -1
                for i, row in df.iterrows():
                    row_str = " ".join([str(v) for v in row.values]).upper()
                    if any(kw in row_str for kw in keywords):
                        header_row = i
                        break
                
                if header_row != -1:
                    new_cols = df.iloc[header_row].values
                    df = df.iloc[header_row + 1:].copy()
                    df.columns = new_cols
                
                # Cleanup column names
                df.columns = [str(c).strip() for c in df.columns]
                
                self.log_debug(f"DETECTED HEADERS: {list(df.columns)}")
                report_type = self.detect_report_type(df)
                self.log_debug(f"REPORT TYPE: {report_type}")
                self.log_debug(f"ROW COUNT: {len(df)}")
                
                if report_type == "GST_REGISTER":
                    self._process_gst_register(df, file)
                elif report_type == "PAYMENT_MODE_REPORT":
                    self._process_payment_mode(df, file)
                elif report_type == "TOTAL_CUSTOMER_REPORT":
                    self._process_total_customer(df, file)
                else:
                    logger.warning(f"Unknown report format in {file}")
                    self.failures.append({
                        "filename": file,
                        "reason": "UNKNOWN_REPORT_TYPE",
                        "headers": list(df.columns),
                        "sample_rows": df.iloc[:5].to_dict(orient='records')
                    })
            else:
                self.log_debug("COULD NOT PARSE FILE AS EXCEL OR TEXT.")
                self.failures.append({
                    "filename": file,
                    "reason": "PARSE_ERROR",
                    "sample_lines": first_20 if 'first_20' in locals() else []
                })

        # Finalize and Save
        self._finalize_and_save()

    def _get_join_key(self, row: pd.Series) -> str:
        vch = str(row.get('Vch No', '')).strip()
        if vch and vch != 'nan' and vch != '':
            return vch
        
        # Fallback key: Date + Name + Amount
        name = str(row.get('Cust Name', row.get('A/c Name', ''))).strip()
        amt = str(row.get('Sale Amt', ''))
        date = self.normalize_date(row.get('Date'))
        return f"{date}_{name}_{amt}"

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
            
            if not rec["invoice_no"]: rec["invoice_no"] = str(row.get('Vch No', ''))
            rec["invoice_date"] = self.normalize_date(row.get('Date'))
            rec["customer_name"] = str(row.get('A/c Name'))
            rec["product_summary"] = str(row.get('Product Name'))
            if filename not in rec["source_files"]: rec["source_files"].append(filename)
            rec["raw_rows"].append(row.to_dict())

    def _process_payment_mode(self, df, filename):
        for _, row in df.iterrows():
            key = self._get_join_key(row)
            self._init_record(key)
            rec = self.raw_records[key]
            
            if not rec["invoice_no"]: rec["invoice_no"] = str(row.get('Vch No', ''))
            
            # Clean numeric values
            def to_float(val):
                if pd.isna(val) or val == '': return 0.0
                try: return float(str(val).replace(",", ""))
                except: return 0.0

            rec["sale_amount"] = to_float(row.get('Sale Amt', 0))
            rec["cash_amount"] = to_float(row.get('Cash Amt', 0))
            rec["bank_amount"] = to_float(row.get('Bank Amt', 0))
            rec["card_amount"] = to_float(row.get('Card Amt', 0))
            rec["advance_amount"] = to_float(row.get('ADV Amt', 0))
            rec["balance_amount"] = to_float(row.get('BAL Amt', 0))
            rec["bhisi_amount"] = to_float(row.get('Bhisi Amt', 0))
            rec["other_amount"] = to_float(row.get('Other Amt', 0))
            
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
            # Avoid duplicate rows if processed multiple times
            rec["payment_rows"] = []
            for mode, amt in modes.items():
                if amt > 0:
                    rec["payment_rows"].append({"payment_mode": mode, "amount": amt})
            
            if filename not in rec["source_files"]: rec["source_files"].append(filename)
            rec["raw_rows"].append(row.to_dict())

    def _process_total_customer(self, df, filename):
        for _, row in df.iterrows():
            # Fallback key
            name = str(row.get('Cust Name')).strip()
            amt = str(row.get('Sale Amt', ''))
            key_base = f"{name}_{amt}"
            
            # Try to find matching record by partial key if Vch No was missing
            match_key = None
            for existing_key in self.raw_records.keys():
                if key_base in existing_key:
                    match_key = existing_key
                    break
            
            if not match_key:
                match_key = key_base
                self._init_record(match_key)
            
            rec = self.raw_records[match_key]
            rec["customer_name"] = name
            rec["mobile"] = str(row.get('Mob No'))
            rec["pan"] = str(row.get('PAN'))
            
            def to_float(val):
                if pd.isna(val) or val == '': return 0.0
                try: return float(str(val).replace(",", ""))
                except: return 0.0

            purc_amt = to_float(row.get('Purc Amt', 0))
            if purc_amt > 0:
                rec["customer_purchase_amount"] = purc_amt
                # Check if already added
                if not any(p["payment_mode"] == "OLD_GOLD_EXCHANGE" for p in rec["payment_rows"]):
                    rec["payment_rows"].append({"payment_mode": "OLD_GOLD_EXCHANGE", "amount": purc_amt})
            
            if filename not in rec["source_files"]: rec["source_files"].append(filename)
            rec["raw_rows"].append(row.to_dict())

    def _finalize_and_save(self):
        final_list = []
        for key, rec in self.raw_records.items():
            pay_sum = sum(p["amount"] for p in rec["payment_rows"])
            if rec["sale_amount"] > 0 and abs(pay_sum - rec["sale_amount"]) > 0.01:
                rec["validation_status"] = "NEEDS_REVIEW"
                rec["unresolved_fields"].append("PAYMENT_TOTAL_MISMATCH")
            elif not rec["invoice_no"] or rec["invoice_no"] == 'nan':
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
        
        with open(FAILURES_OUT, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "count": len(self.failures),
                "failures": self.failures
            }, f, indent=4)
        
        print(f"Import complete. Processed {len(final_list)} records. Failures: {len(self.failures)}")

if __name__ == "__main__":
    importer = PrimeReportImporter()
    importer.import_all()
