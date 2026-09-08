import urllib.request
import json
import os
import sys
import time

def check_url(url, name):
    print(f"Checking {name} at {url}...", end=" ", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.getcode() == 200:
                print("PASSED")
                return True
            else:
                print(f"FAILED (Status: {response.getcode()})")
                return False
    except Exception as e:
        print(f"FAILED (Error: {e})")
        return False

def check_stats():
    url = "http://127.0.0.1:8000/api/prime/dashboard/stats"
    print(f"Verifying dashboard data...", end=" ", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
            count = data.get("totalBillsToday", 0)
            if count > 0:
                print(f"PASSED ({count} records found)")
                return True
            else:
                print("FAILED (0 records in dashboard)")
                return False
    except Exception as e:
        print(f"FAILED (Error: {e})")
        return False

def check_files():
    path = r"C:\Aradhana\PrimeExports\JSON\prime_report_import.json"
    print(f"Checking for report JSON...", end=" ", flush=True)
    if os.path.exists(path):
        print("PASSED")
        return True
    else:
        print("FAILED (File not found)")
        return False

if __name__ == "__main__":
    print("====================================================")
    print("      ARADHANA AUDITOR SYSTEM HEALTH CHECK")
    print("====================================================\n")
    
    overall_pass = True
    
    # 1. Check Backend
    if not check_url("http://127.0.0.1:8000/api/prime/dashboard/stats", "Backend API"):
        overall_pass = False
        
    # 2. Check Frontend
    if not check_url("http://localhost:5173", "Frontend UI"):
        overall_pass = False
        
    # 3. Check Files
    if not check_files():
        overall_pass = False
        
    # 4. Check Data
    if overall_pass:
        if not check_stats():
            overall_pass = False
            
    print("\n----------------------------------------------------")
    if overall_pass:
        print("SYSTEM STATUS: ONLINE / HEALTHY")
        sys.exit(0)
    else:
        print("SYSTEM STATUS: DEGRADED / OFFLINE")
        sys.exit(1)
