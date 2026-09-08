import logging
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models import Bill, Payment, BankAlert, AuditLog, Cheque
from datetime import datetime
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Reconciliation_Orchestrator")

def reconcile_bank_payments():
    db = SessionLocal()
    try:
        # 1. Get all pending bank/cheque bills
        pending_bills = db.query(Bill).filter(Bill.status.in_(["Yellow", "Blue"])).all()
        
        for bill in pending_bills:
            # Match logic
            amount = bill.total_amount
            mode = bill.payment_mode
            
            # Find matching bank alert
            # Criteria: Exact amount, and not already linked
            # For simplicity, we search for alerts with same amount and compatible mode
            query = db.query(BankAlert).filter(BankAlert.amount == amount)
            
            # If we have a UTR/Cheque No, use it
            if bill.reference_no:
                query = query.filter(BankAlert.utr_reference == bill.reference_no)
            
            match = query.first()
            
            if match:
                # Deterministic Match Found
                old_status = bill.status
                bill.status = "Green"
                bill.status_text = "Cleared (Bank Verified)"
                bill.review_required = 0
                
                # Update Cheque if needed
                if mode == "CHEQUE":
                    cheque = db.query(Cheque).filter(Cheque.bill_id == bill.id).first()
                    if cheque:
                        cheque.status = "Green"
                        cheque.cleared_at = datetime.now()
                
                # Update Payments
                for payment in db.query(Payment).filter(Payment.bill_id == bill.id).all():
                    payment.status = "Green"

                # Audit Log
                audit = AuditLog(
                    entity_type="Bill",
                    entity_id=bill.id,
                    action="BANK_RECONCILIATION",
                    old_status=old_status,
                    new_status="Green",
                    actor="SYSTEM",
                    metadata_json=json.dumps({"bank_alert_id": match.id, "utr": match.utr_reference})
                )
                db.add(audit)
                
                logger.info(f"Reconciled Bill {bill.bill_number} with Bank Alert {match.id}")
        
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Reconciliation error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reconcile_bank_payments()
