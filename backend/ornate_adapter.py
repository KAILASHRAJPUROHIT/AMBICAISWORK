from typing import Dict, Any
from backend.erp_models import CustomerRecord, BillRecord, PaymentRecord, ChequeRecord

def parse_ornate_customer(raw: Dict[str, Any]) -> CustomerRecord:
    return CustomerRecord(
        customer_id=str(raw["CustomerID"]),
        customer_name=str(raw["FullName"]),
        mobile=str(raw["MobileNo"]),
        city=str(raw["CityName"])
    )

def parse_ornate_bill(raw: Dict[str, Any]) -> BillRecord:
    return BillRecord(
        bill_id=str(raw["BillID"]),
        customer_id=str(raw["CustomerID"]),
        amount=float(raw["BillAmount"]),
        bill_date=str(raw["Date"]),
        delivery_status=str(raw["Delivery"])
    )

def parse_ornate_payment(raw: Dict[str, Any]) -> PaymentRecord:
    return PaymentRecord(
        payment_id=str(raw["PayID"]),
        bill_id=str(raw["BillID"]),
        amount=float(raw["Amount"]),
        payment_mode=str(raw["Mode"]),
        utr_reference=str(raw["Reference"]) if raw.get("Reference") else None,
        payment_date=str(raw["PayDate"])
    )

def parse_ornate_cheque(raw: Dict[str, Any]) -> ChequeRecord:
    return ChequeRecord(
        cheque_id=str(raw["ID"]),
        bill_id=str(raw["BillID"]),
        cheque_number=str(raw["Number"]),
        bank_name=str(raw["Bank"]),
        amount=float(raw["Amount"]),
        deposit_date=str(raw["Date"]),
        clearance_status=str(raw["Status"])
    )
