from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from .database import engine, SessionLocal, Base
from .models import User, Bill, Payment, BankAlert, SMSAlert, Cheque, AuditLog

Base.metadata.create_all(bind=engine)

app = FastAPI()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/users/")
def create_user(username: str, email: str, db: Session = Depends(get_db)):
    db_user = User(username=username, email=email)
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

@app.post("/bills/")
def create_bill(user_id: int, amount: float, status: str = "Yellow", db: Session = Depends(get_db)):
    db_bill = Bill(user_id=user_id, amount=amount, status=status)
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

@app.post("/payments/")
def create_payment(bill_id: int, amount: float, status: str = "Yellow", db: Session = Depends(get_db)):
    db_payment = Payment(bill_id=bill_id, amount=amount, status=status)
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

@app.post("/bank_alerts/")
def create_bank_alert(user_id: int, message: str, status: str = "Yellow", db: Session = Depends(get_db)):
    db_bank_alert = BankAlert(user_id=user_id, message=message, status=status)
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

@app.post("/sms_alerts/")
def create_sms_alert(user_id: int, message: str, status: str = "Yellow", db: Session = Depends(get_db)):
    db_sms_alert = SMSAlert(user_id=user_id, message=message, status=status)
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

@app.post("/cheques/")
def create_cheque(user_id: int, amount: float, status: str = "Yellow", db: Session = Depends(get_db)):
    db_cheque = Cheque(user_id=user_id, amount=amount, status=status)
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

@app.post("/audit_logs/")
def create_audit_log(user_id: int, action: str, details: str, status: str = "Yellow", db: Session = Depends(get_db)):
    db_audit_log = AuditLog(user_id=user_id, action=action, details=details, status=status)
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
