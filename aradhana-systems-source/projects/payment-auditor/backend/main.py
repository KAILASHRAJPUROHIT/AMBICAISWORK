from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .database import engine, SessionLocal, Base
from .models import User, Bill, Payment, BankAlert, SMSAlert, Cheque, AuditLog
from .schemas import ReconciliationDecision, ReviewQueueItem, RoutingResult 
from reconciliation_engine import reconcile_transactions 
from review_queue import route_review 
from .api_routes import router
from .auth import require_admin, require_admin_or_owner, require_admin_or_accountant

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(router)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/users/", dependencies=[Depends(require_admin)])
def create_user(username: str, email: str, db: Session = Depends(get_db)):
    db_user = User(name=username, role="STAFF")
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/users/{user_id}")
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

@app.post("/bills/", dependencies=[Depends(require_admin)])
def create_bill(user_id: int, amount: float, status: str = "Yellow", db: Session = Depends(get_db)):
    db_bill = Bill(
        bill_number=f"BILL-{datetime.now().timestamp()}", 
        customer_name=f"User {user_id}", 
        amount=amount, 
        status=status,
        is_test_data=True
    )
    db.add(db_bill)
    db.commit()
    db.refresh(db_bill)
    return db_bill

@app.get("/bills/{bill_id}")
def read_bill(bill_id: int, db: Session = Depends(get_db)):
    db_bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if db_bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    return db_bill

@app.post("/payments/", dependencies=[Depends(require_admin)])
def create_payment(bill_id: int, amount: float, status: str = "Yellow", db: Session = Depends(get_db)):
    db_payment = Payment(bill_id=bill_id, amount=amount, mode="CASH", status=status)
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)
    return db_payment

@app.get("/payments/{payment_id}")
def read_payment(payment_id: int, db: Session = Depends(get_db)):
    db_payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if db_payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return db_payment

@app.post("/bank_alerts/", dependencies=[Depends(require_admin)])
def create_bank_alert(user_id: int, message: str, status: str = "Yellow", db: Session = Depends(get_db)):
    db_bank_alert = BankAlert(bank_name="Generic Bank", amount=0, sender=f"User {user_id}", received_at=datetime.now(), raw_text=message)
    db.add(db_bank_alert)
    db.commit()
    db.refresh(db_bank_alert)
    return db_bank_alert

@app.get("/bank_alerts/{alert_id}")
def read_bank_alert(alert_id: int, db: Session = Depends(get_db)):
    db_bank_alert = db.query(BankAlert).filter(BankAlert.id == alert_id).first()
    if db_bank_alert is None:
        raise HTTPException(status_code=404, detail="Bank Alert not found")
    return db_bank_alert

@app.post("/sms_alerts/", dependencies=[Depends(require_admin)])
def create_sms_alert(user_id: int, message: str, status: str = "Yellow", db: Session = Depends(get_db)):
    db_sms_alert = SMSAlert(phone_source="Unknown", amount=0, received_at=datetime.now(), raw_text=message)
    db.add(db_sms_alert)
    db.commit()
    db.refresh(db_sms_alert)
    return db_sms_alert

@app.get("/sms_alerts/{alert_id}")
def read_sms_alert(alert_id: int, db: Session = Depends(get_db)):
    db_sms_alert = db.query(SMSAlert).filter(SMSAlert.id == alert_id).first()
    if db_sms_alert is None:
        raise HTTPException(status_code=404, detail="SMS Alert not found")
    return db_sms_alert

@app.post("/cheques/", dependencies=[Depends(require_admin)])
def create_cheque(user_id: int, amount: float, status: str = "Yellow", db: Session = Depends(get_db)):
    db_cheque = Cheque(bill_id=user_id, cheque_number="000000", bank_name="Generic Bank", amount=amount, status=status)
    db.add(db_cheque)
    db.commit()
    db.refresh(db_cheque)
    return db_cheque

@app.get("/cheques/{cheque_id}")
def read_cheque(cheque_id: int, db: Session = Depends(get_db)):
    db_cheque = db.query(Cheque).filter(Cheque.id == cheque_id).first()
    if db_cheque is None:
        raise HTTPException(status_code=404, detail="Cheque not found")
    return db_cheque

@app.post("/audit_logs/", dependencies=[Depends(require_admin_or_owner)])
def create_audit_log(user_id: int, action: str, details: str, status: str = "Yellow", db: Session = Depends(get_db)):
    db_audit_log = AuditLog(entity_type="manual", entity_id=user_id, action=action, actor="SYSTEM", metadata_json=details)
    db.add(db_audit_log)
    db.commit()
    db.refresh(db_audit_log)
    return db_audit_log

@app.get("/audit_logs/{log_id}")
def read_audit_log(log_id: int, db: Session = Depends(get_db)):
    db_audit_log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if db_audit_log is None:
        raise HTTPException(status_code=404, detail="Audit Log not found")
    return db_audit_log

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/status-colors")
def status_colors():
    return {
        "Yellow": "#FFFF99",
        "Orange": "#FFA500",
        "Red": "#FF0000",
        "Green": "#008000",
        "Blue": "#ADD8E6",
        "Purple": "#800080"
    }

@app.post("/review_queue/", response_model=ReviewQueueItem, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_or_accountant)])
def create_review_queue_item(item: ReviewQueueItem, db: Session = Depends(get_db)):
    decision = reconcile_transactions(
        bills=db.query(Bill).filter(Bill.id == item.entity_id).all(),
        payments=db.query(Payment).filter(Payment.bill_id == item.entity_id).all(),
        bank_alerts=db.query(BankAlert).filter(BankAlert.utr_reference == item.entity_id).all(),
        sms_alerts=db.query(SMSAlert).filter(SMSAlert.utr_reference == item.entity_id).all(),
        cheques=db.query(Cheque).filter(Cheque.bill_id == item.entity_id).all()
    )
    routing_result = route_review(decision.dict())
    
    new_item = ReviewQueueItem(
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        current_status=decision.status,
        proposed_status=item.proposed_status,
        risk_flags=decision.risk_flags,
        requires_owner_escalation=routing_result["escalation_required"],
        created_at=datetime.utcnow()
    )
    
    # db.add(new_item)
    # db.commit()
    # db.refresh(new_item)
    
    return new_item
