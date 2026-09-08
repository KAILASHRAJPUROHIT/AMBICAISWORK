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
        self.stats = {
            "total_imported_rows": 0,
            "transaction_rows": 0,
            "customer_enrichment_rows": 0,
            "linked_advance_records": 0,
            "removed_fake_records": 0
        }
        os.makedirs(INPUT_DIR, exist_ok=True)

    def log_debug(self, msg: str):
        debug_logger.debug(msg)

    def _is_ledger_name(self, name: str) -> bool:
        if not name or name == 'nan': return True
        name_up = str(name).upper()
        ledger_keywords = ["A/C", "AC", "CASH", "BANK", "SALE GOLD", "PURCHASE GOLD", "SALE SILVER", "GST", "TAX", "OPENING", "CLOSING"]
        return any(kw in name_up for kw in ledger_keywords)

    def detect_report_type(self, df: pd.DataFrame) -> str:
        cols = " ".join([str(c) for c in df.columns]).upper()
        if "BOOK NAME" in cols and "VCH NO" in cols:
            return "GST_REGISTER"
        if "SALE AMT" in cols and ("CASH AMT" in cols or "CASH" in cols):
            return "PAYMENT_MODE_REPORT"
        if "CUST NAME" in cols and "MOB NO" in cols and "PURC AMT" in cols:
            return "TOTAL_CUSTOMER_REPORT"
        
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
            return pd.to_datetime(val).strftime("%d/%m/%Y")
        except: return str(val)

    def to_float(self, val):
        if pd.isna(val) or val == '': return 0.0
        try: return float(str(val).replace(",", ""))
        except: return 0.0

    def try_parse_as_text(self, path: str) -> Optional[pd.DataFrame]:
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [f.readline() for _ in range(100)]
            content = "".join(lines)
            if '\t' in content: delim = '\t'
            elif ',' in content: delim = ','
            else: delim = r'\s{2,}'
            
            header_row_idx = -1
            keywords = ["VCH NO", "BOOK NAME", "CUST NAME", "SALE AMT", "MOB NO"]
            for i, line in enumerate(lines):
                if any(kw in line.upper() for kw in keywords):
                    header_row_idx = i
                    break
            if header_row_idx == -1: return None
            df = pd.read_csv(path, sep=delim, skiprows=header_row_idx, engine='python', on_bad_lines='skip')
            return df
        except Exception as e:
            self.log_debug(f"Text parse attempt failed: {e}")
            return None

    def _get_val(self, row: pd.Series, keys: List[str], default: Any = "") -> Any:
        for k in keys:
            if k in row.index:
                val = row[k]
                if pd.notna(val): return val
        return default

    def import_all(self):
        print(f"SEARCH_FOLDER={INPUT_DIR}")
        files = [f for f in os.listdir(INPUT_DIR) if f.endswith(('.xls', '.xlsx', '.csv', '.txt'))]
        print(f"FILES_FOUND={len(files)}")
        
        if not files:
            print("NO_MANUAL_REPORT_FILES_FOUND")
            return

        file_data = []
        for file in files:
            path = os.path.join(INPUT_DIR, file)
            df = None
            if file.endswith(('.xls', '.xlsx')):
                try: df = pd.read_excel(path)
                except: pass
            if df is None: df = self.try_parse_as_text(path)

            if df is not None:
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
                
                df.columns = [str(c).strip() for c in df.columns]
                rtype = self.detect_report_type(df)
                file_data.append((file, df, rtype))

        # Sort Priority: PAYMENT_MODE_REPORT Establishment
        file_data.sort(key=lambda x: 0 if x[2] == "PAYMENT_MODE_REPORT" else (1 if x[2] == "GST_REGISTER" else 2))

        for file, df, rtype in file_data:
            self.log_debug(f"Processing {file} as {rtype}")
            if rtype == "GST_REGISTER":
                self._process_gst_register(df, file)
            elif rtype == "PAYMENT_MODE_REPORT":
                self._process_payment_mode(df, file)
            elif rtype == "TOTAL_CUSTOMER_REPORT":
                self._process_total_customer(df, file)

        self._match_advance_vouchers()
        self._finalize_and_save()

    def _get_join_key(self, row: pd.Series) -> str:
        vch = str(row.get('Vch No', '')).strip()
        if vch and vch != 'nan' and vch != '' and vch != '---':
            return vch
        return None

    def _init_record(self, key, source_report):
        if key not in self.raw_records:
            self.raw_records[key] = {
                "invoice_no": key,
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
                "raw_rows": [],
                "source_report": source_report,
                "linked_sale_voucher": None,
                "linked_advance_voucher": None
            }

    def _process_payment_mode(self, df, filename):
        for _, row in df.iterrows():
            self.stats["total_imported_rows"] += 1
            key = self._get_join_key(row)
            if not key:
                self.stats["removed_fake_records"] += 1
                continue
            
            self._init_record(key, "PAYMENT_MODE")
            rec = self.raw_records[key]
            rec["source_report"] = "PAYMENT_MODE"
            self.stats["transaction_rows"] += 1
            
            # Master Authority for Name
            rec["customer_name"] = str(self._get_val(row, ['Cust Name', 'Cust Name - Mob No - PAN', 'A/c Name'], ""))
            rec["sale_amount"] = self.to_float(self._get_val(row, ['Sale Amt', 'Sale Amt.']))
            rec["cash_amount"] = self.to_float(self._get_val(row, ['Cash Amt', 'Cash Amt.']))
            rec["bank_amount"] = self.to_float(self._get_val(row, ['Bank Amt', 'Bank Amt.']))
            rec["card_amount"] = self.to_float(self._get_val(row, ['Card Amt', 'Card Amt.']))
            rec["advance_amount"] = self.to_float(self._get_val(row, ['ADV Amt', 'ADV Amt.']))
            rec["balance_amount"] = self.to_float(self._get_val(row, ['BAL Amt', 'BAL Amt.']))
            rec["bhisi_amount"] = self.to_float(self._get_val(row, ['Bhisi Amt', 'Bhisi Amt.']))
            rec["other_amount"] = self.to_float(self._get_val(row, ['Other Amt', 'Other Amt.']))
            
            modes = {
                "CASH": rec["cash_amount"],
                "BANK": rec["bank_amount"],
                "CARD": rec["card_amount"],
                "ADVANCE": rec["advance_amount"],
                "BALANCE": rec["balance_amount"],
                "BHISI": rec["bhisi_amount"],
                "OTHER": rec["other_amount"]
            }
            rec["payment_rows"] = []
            for mode, amt in modes.items():
                if amt > 0: rec["payment_rows"].append({"payment_mode": mode, "amount": amt})
            
            if filename not in rec["source_files"]: rec["source_files"].append(filename)
            rec["raw_rows"].append(row.to_dict())

    def _process_gst_register(self, df, filename):
        for _, row in df.iterrows():
            self.stats["total_imported_rows"] += 1
            key = self._get_join_key(row)
            if not key: continue
            
            if key not in self.raw_records:
                self._init_record(key, "GST_REGISTER")
            
            rec = self.raw_records[key]
            # Name Preservation Rule
            new_name = str(self._get_val(row, ['A/c Name', 'Cust Name', 'Cust Name - Mob No - PAN'], ""))
            if not rec["customer_name"] or (self._is_ledger_name(rec["customer_name"]) and not self._is_ledger_name(new_name)):
                rec["customer_name"] = new_name
            elif self._is_ledger_name(new_name) and rec["customer_name"] and not self._is_ledger_name(rec["customer_name"]) and rec["customer_name"] != new_name:
                self.log_debug(f"customer_name_overwrite_blocked for {key}: '{rec['customer_name']}' preserved over '{new_name}'")

            rec["invoice_date"] = self.normalize_date(self._get_val(row, ['Date', 'Invoice Date']))
            rec["product_summary"] = str(self._get_val(row, ['Product Name', 'Prd Name']))
            rec["taxable_amount"] = self.to_float(self._get_val(row, ['Taxable Amt', 'Taxable Amt.']))
            rec["cgst"] = self.to_float(self._get_val(row, ['CGST Amt', 'CGST']))
            rec["sgst"] = self.to_float(self._get_val(row, ['SGST Amt', 'SGST']))
            
            if filename not in rec["source_files"]: rec["source_files"].append(filename)
            rec["raw_rows"].append(row.to_dict())

    def _process_total_customer(self, df, filename):
        for _, row in df.iterrows():
            self.stats["total_imported_rows"] += 1
            self.stats["customer_enrichment_rows"] += 1
            
            name = str(self._get_val(row, ['Cust Name', 'A/c Name'], "")).strip()
            # Remove branch/id from name if present: Dhanraj Santosh Kulabkar(1347/25-26)
            clean_name = re.sub(r'\(.*\)', '', name).strip()
            
            amt = self.to_float(self._get_val(row, ['Sale Amt', 'Sale Amt.']))
            
            match_found = False
            for key, rec in self.raw_records.items():
                rec_name_clean = re.sub(r'\(.*\)', '', str(rec["customer_name"])).strip()
                if rec_name_clean == clean_name and abs(rec["sale_amount"] - amt) < 0.01:
                    rec["mobile"] = str(self._get_val(row, ['Mob No', 'Mob No.']))
                    rec["pan"] = str(self._get_val(row, ['PAN']))
                    rec["customer_purchase_amount"] = self.to_float(self._get_val(row, ['Purc Amt', 'Purc Amt.']))
                    match_found = True
                    break
            
            if not match_found:
                self.log_debug(f"Customer enrichment skipped: No matching sale for {clean_name} ₹{amt}")

    def _match_advance_vouchers(self):
        advances = [r for r in self.raw_records.values() if str(r["invoice_no"]).startswith("P2-")]
        sales = [r for r in self.raw_records.values() if r["advance_amount"] > 0]
        
        for adv in advances:
            adv_amt = adv["sale_amount"]
            adv_name = re.sub(r'\(.*\)', '', str(adv["customer_name"])).strip()
            
            candidates = [s for s in sales if abs(s["advance_amount"] - adv_amt) < 0.01 and re.sub(r'\(.*\)', '', str(s["customer_name"])).strip() == adv_name]
            
            if len(candidates) == 1:
                sale = candidates[0]
                adv["linked_sale_voucher"] = sale["invoice_no"]
                sale["linked_advance_voucher"] = adv["invoice_no"]
                self.stats["linked_advance_records"] += 1
                self.log_debug(f"LINKED: Advance {adv['invoice_no']} -> Sale {sale['invoice_no']} (₹{adv_amt})")
            elif len(candidates) > 1:
                adv["validation_status"] = "ORANGE"
                adv["unresolved_fields"].append("AMBIGUOUS_ADVANCE_LINKAGE")

    def _finalize_and_save(self):
        final_list = []
        for rec in self.raw_records.values():
            if rec["source_report"] != "PAYMENT_MODE":
                continue

            pay_sum = sum(p["amount"] for p in rec["payment_rows"])
            has_cheque = any(p["payment_mode"] == "CHEQUE" for p in rec["payment_rows"])
            
            if rec["invoice_no"].startswith("P2-"):
                if rec["linked_sale_voucher"]:
                    rec["validation_status"] = "GREEN" 
                else:
                    rec["validation_status"] = "YELLOW" 
                    rec["unresolved_fields"].append("ADVANCE_AWAITING_SALE")
            elif has_cheque:
                rec["validation_status"] = "BLUE"
                rec["unresolved_fields"].append("CHEQUE_PAYMENT_PENDING_REALIZATION")
            elif abs(pay_sum - rec["sale_amount"]) < 0.01:
                rec["validation_status"] = "GREEN"
            else:
                rec["validation_status"] = "RED"
                rec["unresolved_fields"].append("PAYMENT_TOTAL_MISMATCH")
            
            final_list.append(rec)

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "count": len(final_list),
            "stats": self.stats,
            "records": final_list
        }
        
        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4)
        
        print(f"Import complete.")
        print(f"Total Rows: {self.stats['total_imported_rows']}")
        print(f"Transaction Records: {self.stats['transaction_rows']}")
        print(f"Customer Enrichment: {self.stats['customer_enrichment_rows']}")
        print(f"Advance Links: {self.stats['linked_advance_records']}")
        print(f"Fake Records Purged: {self.stats['removed_fake_records']}")

if __name__ == "__main__":
    importer = PrimeReportImporter()
    importer.import_all()
