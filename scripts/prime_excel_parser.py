import sys
import os
import json
import pandas as pd
from datetime import datetime

# Configuration
EXPORT_BASE = r"C:\Aradhana\PrimeExports"
JSON_OUT = os.path.join(EXPORT_BASE, "JSON", "prime_sales_report.json")

def parse_excel(file_path):
    print(f"Parsing Excel: {file_path}")
    try:
        # Prime typically exports .xls which pandas/xlrd can read.
        # We might need to skip some header rows. 
        # Usually, Prime reports have titles in first few rows.
        df = pd.read_excel(file_path)
        
        # Heuristic to find the real header row
        # We look for a row containing 'Vch No' or 'Date'
        header_row_idx = 0
        for i, row in df.iterrows():
            row_str = " ".join([str(val) for val in row.values])
            if 'Vch No' in row_str or 'Bill No' in row_str:
                header_row_idx = i
                break
        
        # Reload with correct header
        df = pd.read_excel(file_path, skiprows=header_row_idx + 1)
        
        # Rename columns to standard internal names if possible
        # Map: Date, Vch No, Customer, Product, Taxable Amt, CGST, SGST, Sale Amt, Cash Amt, Bank Amt, Card Amt, BAL Amt, Bhisi Amt, ADV Amt, Other Amt
        
        # Example mapping (needs refinement based on actual excel structure)
        # We'll use a fuzzy match or positional if names vary
        
        records = []
        for _, row in df.iterrows():
            # Skip empty rows
            if pd.isna(row.get('Vch No')) and pd.isna(row.get('Bill No')):
                continue
                
            record = {
                "date": str(row.get('Date', '')),
                "invoice_no": str(row.get('Vch No', row.get('Bill No', ''))),
                "customer": str(row.get('Customer', row.get('A/c Name', ''))),
                "product": str(row.get('Product', '')),
                "taxable_amt": float(row.get('Taxable Amt', 0.0)),
                "cgst": float(row.get('CGST', 0.0)),
                "sgst": float(row.get('SGST', 0.0)),
                "sale_amt": float(row.get('Sale Amt', 0.0)),
                "cash_amt": float(row.get('Cash Amt', 0.0)),
                "bank_amt": float(row.get('Bank Amt', 0.0)),
                "card_amt": float(row.get('Card Amt', 0.0)),
                "bal_amt": float(row.get('BAL Amt', 0.0)),
                "bhisi_amt": float(row.get('Bhisi Amt', 0.0)),
                "adv_amt": float(row.get('ADV Amt', 0.0)),
                "other_amt": float(row.get('Other Amt', 0.0))
            }
            records.append(record)

        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "source_file": file_path,
                "count": len(records),
                "records": records
            }, f, indent=4)
        
        print(f"Success: Parsed {len(records)} records to {JSON_OUT}")

    except Exception as e:
        print(f"Error parsing Excel: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        parse_excel(sys.argv[1])
    else:
        print("No file path provided.")
