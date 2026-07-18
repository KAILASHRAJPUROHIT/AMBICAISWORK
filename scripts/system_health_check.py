import os
import json
import platform
import struct
import socket
import imaplib
from datetime import datetime
from dotenv import load_dotenv
import psutil

load_dotenv()

# Configuration
PATHS = {
    "snapshot_base": r"C:\Aradhana\Snapshots",
    "prime_exe": r"C:\Aradhana\Prime\FA.exe",
    "venv32": r"C:\Aradhana\venv32\Scripts\python.exe",
    "json_out": r"C:\Aradhana\PrimeExports\JSON",
    "logs_out": r"C:\Aradhana\PrimeExports\Logs",
    "audit_logs": r"C:\Aradhana\AuditLogs"
}

def check_paths():
    results = {}
    for name, path in PATHS.items():
        exists = os.path.exists(path)
        results[name] = {"path": path, "exists": exists}
    return results

def check_imap():
    user = os.getenv("IMAP_USER")
    password = os.getenv("IMAP_PASSWORD")
    host = os.getenv("IMAP_HOST", "imap.gmail.com")
    
    if not user or not password:
        return {"status": "FAIL", "reason": "Credentials missing in .env"}
    
    try:
        mail = imaplib.IMAP4_SSL(host, timeout=10)
        mail.login(user, password)
        status, labels = mail.list()
        mail.logout()
        return {"status": "PASS", "labels_found": len(labels) if status == 'OK' else 0}
    except Exception as e:
        return {"status": "FAIL", "reason": str(e)}

def run_health_check():
    print("Starting System Health Check...")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "os": platform.platform(),
        "python_bitness": struct.calcsize("P") * 8,
        "checks": {
            "paths": check_paths(),
            "imap": check_imap()
        },
        "overall_status": "PASS"
    }

    # Logic for overall status
    if report["python_bitness"] != 64: # Host script is 64-bit
         pass # OK
    
    path_fails = [p for p in report["checks"]["paths"].values() if not p["exists"]]
    if path_fails:
        report["overall_status"] = "WARNING"
        if not report["checks"]["paths"]["venv32"]["exists"]:
            report["overall_status"] = "FAIL"

    if report["checks"]["imap"]["status"] == "FAIL":
        report["overall_status"] = "FAIL"

    output_path = os.path.join(PATHS["json_out"], "system_health_report.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)
    
    print(f"Health check complete. Status: {report['overall_status']}")
    print(f"Report saved to {output_path}")
    return report

if __name__ == "__main__":
    run_health_check()
