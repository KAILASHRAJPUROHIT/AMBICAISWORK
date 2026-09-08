from pydantic import BaseModel
from typing import Optional

class CustomerRecord(BaseModel):
    customer_id: str
    customer_name: str
    mobile: str
    city: str

class BillRecord(BaseModel):
    bill_id: str
    customer_id: str
    amount: float
    bill_date: str
    delivery_status: str

class PaymentRecord(BaseModel):
    payment_id: str
    bill_id: str
    amount: float
    payment_mode: str
    utr_reference: Optional[str] = None
    payment_date: str

class ChequeRecord(BaseModel):
    cheque_id: str
    bill_id: str
    cheque_number: str
    bank_name: str
    amount: float
    deposit_date: str
    clearance_status: str
