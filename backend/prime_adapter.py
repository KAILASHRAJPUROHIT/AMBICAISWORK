from typing import Dict, Any
from backend.erp_models import CustomerRecord, BillRecord, PaymentRecord, ChequeRecord

def parse_prime_customer(raw: Dict[str, Any]) -> CustomerRecord:
    return CustomerRecord(
        customer_id=str(raw["cust_id"]),
        customer_name=str(raw["name"]),
        mobile=str(raw["phone"]),
        city=str(raw["location"])
    )

def parse_prime_bill(raw: Dict[str, Any]) -> BillRecord:
    return BillRecord(
        bill_id=str(raw["invoice_no"]),
        customer_id=str(raw["client_ref"]),
        amount=float(raw["total_val"]),
        bill_date=str(raw["inv_date"]),
        delivery_status=str(raw["status"])
    )

def parse_prime_payment(raw: Dict[str, Any]) -> PaymentRecord:
    return PaymentRecord(
        payment_id=str(raw["txn_id"]),
        bill_id=str(raw["invoice_no"]),
        amount=float(raw["val"]),
        payment_mode=str(raw["type"]),
        utr_reference=str(raw["utr"]) if raw.get("utr") else None,
        payment_date=str(raw["date"])
    )

def parse_prime_cheque(raw: Dict[str, Any]) -> ChequeRecord:
    return ChequeRecord(
        cheque_id=str(raw["chq_id"]),
        bill_id=str(raw["invoice_no"]),
        cheque_number=str(raw["chq_no"]),
        bank_name=str(raw["bank"]),
        amount=float(raw["val"]),
        deposit_date=str(raw["dep_date"]),
        clearance_status=str(raw["status"])
    )
