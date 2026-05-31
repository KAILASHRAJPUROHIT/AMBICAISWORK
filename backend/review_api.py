from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import json
import os

app = FastAPI(title="Aradhana Payment Auditor - Review API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to the frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class ReviewAction(BaseModel):
    invoice_no: str
    status: str # 'APPROVED', 'REJECTED'
    comment: str
    accountant_id: str

class ReconciliationResult(BaseModel):
    invoice_no: str
    status: str
    reason: Optional[str]
    timestamp: str
    details: dict

# Mock Storage Paths
AUDIT_LOG_DIR = "C:/Aradhana/AuditLogs"
EXTRACTION_PATH = "C:/Aradhana/PrimeExports/JSON/daily_extract.json"
MANUAL_REPORT_PATH = "C:/Aradhana/PrimeExports/JSON/prime_report_import.json"
os.makedirs(AUDIT_LOG_DIR, exist_ok=True)

@app.get("/api/prime/manual-report-import/latest")
async def get_latest_manual_import():
    if not os.path.exists(MANUAL_REPORT_PATH):
        raise HTTPException(status_code=404, detail="Latest manual report import file not found.")
    
    try:
        with open(MANUAL_REPORT_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            # Fix NaN values in JSON (common from pandas export)
            content = content.replace("NaN", "null")
            data = json.loads(content)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading manual import file: {e}")

@app.get("/api/prime/dashboard/stats")
async def get_dashboard_stats():
    if not os.path.exists(MANUAL_REPORT_PATH):
        # Fallback to defaults if no report
        return {
            "totalBillsToday": 0,
            "verified": 0,
            "pendingReview": 0,
            "totalCollection": 0.0,
            "cashCollection": 0.0,
            "bankCollection": 0.0,
            "cardCollection": 0.0,
            "advanceCollection": 0.0,
            "matchAccuracy": 0.0
        }

    try:
        with open(MANUAL_REPORT_PATH, "r", encoding="utf-8") as f:
            content = f.read().replace("NaN", "null")
            data = json.loads(content)
        
        records = data.get("records", [])
        total_bills = len([r for r in records if r.get("invoice_no")])
        pending = len([r for r in records if r.get("validation_status") == "NEEDS_REVIEW"])
        verified = len([r for r in records if r.get("validation_status") == "GREEN"])
        
        total_sale = sum(r.get("sale_amount", 0.0) for r in records)
        cash = sum(r.get("cash_amount", 0.0) for r in records)
        bank = sum(r.get("bank_amount", 0.0) for r in records)
        card = sum(r.get("card_amount", 0.0) for r in records)
        adv = sum(r.get("advance_amount", 0.0) for r in records)

        return {
            "totalBillsToday": total_bills,
            "verified": verified,
            "pendingReview": pending,
            "totalCollection": total_sale,
            "cashCollection": cash,
            "bankCollection": bank,
            "cardCollection": card,
            "advanceCollection": adv,
            "matchAccuracy": round((verified / total_bills * 100), 2) if total_bills > 0 else 0.0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dashboard stats error: {e}")

@app.get("/api/prime/extractions/latest")
async def get_latest_extraction():
    if not os.path.exists(EXTRACTION_PATH):
        raise HTTPException(status_code=404, detail="Latest extraction file not found.")
    
    try:
        with open(EXTRACTION_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading extraction file: {e}")

@app.get("/api/reconciliations", response_model=List[ReconciliationResult])
async def get_reconciliations():
    if not os.path.exists(MANUAL_REPORT_PATH):
        return []
    
    try:
        with open(MANUAL_REPORT_PATH, "r", encoding="utf-8") as f:
            content = f.read().replace("NaN", "null")
            data = json.loads(content)
        
        records = data.get("records", [])
        return [
            {
                "invoice_no": r.get("invoice_no") or "---",
                "status": "GREEN" if r.get("validation_status") == "GREEN" else "RED",
                "reason": r.get("unresolved_fields")[0] if r.get("unresolved_fields") else None,
                "timestamp": data.get("timestamp"),
                "details": {
                    "customer": r.get("customer_name"),
                    "total": r.get("sale_amount"),
                    "payments": sum(p.get("amount", 0.0) for p in r.get("payment_rows", [])),
                    "mode": r.get("payment_rows")[0].get("payment_mode") if r.get("payment_rows") else "MULTI"
                }
            } for r in records
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/reports/owner")
async def get_owner_report():
    if not os.path.exists(MANUAL_REPORT_PATH):
         return {"daily_summary": {"generated_at": datetime.now().isoformat(), "processed_count": 0, "resolved_reviews": 0}}
    
    try:
        with open(MANUAL_REPORT_PATH, "r", encoding="utf-8") as f:
            content = f.read().replace("NaN", "null")
            data = json.loads(content)
        
        records = data.get("records", [])
        processed = len(records)
        resolved = len([r for r in records if r.get("validation_status") == "GREEN"])
        
        return {
            "daily_summary": {
                "generated_at": data.get("timestamp"),
                "processed_count": processed,
                "resolved_reviews": resolved
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/review")
async def review_invoice(action: ReviewAction):
    # MANDATE: All actions must create audit logs
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": "ACCOUNTANT_REVIEW",
        "invoice_no": action.invoice_no,
        "action": action.status,
        "comment": action.comment,
        "accountant": action.accountant_id
    }
    
    log_filename = f"REVIEW_{action.invoice_no.replace('/', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    log_path = os.path.join(AUDIT_LOG_DIR, log_filename)
    
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_entry, f, indent=4)
    
    return {"status": "success", "audit_log": log_path}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
