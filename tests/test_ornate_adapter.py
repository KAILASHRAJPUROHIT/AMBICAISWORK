import pytest
from backend.ornate_adapter import parse_ornate_customer, parse_ornate_bill, parse_ornate_payment, parse_ornate_cheque

def test_valid_ornate_customer():
    raw = {"CustomerID": "O1", "FullName": "Bob", "MobileNo": "888", "CityName": "LA"}
    record = parse_ornate_customer(raw)
    assert record.customer_id == "O1"
    assert record.customer_name == "Bob"

def test_valid_ornate_bill():
    raw = {"BillID": "B1", "CustomerID": "O1", "BillAmount": "200.0", "Date": "2026-05-05", "Delivery": "Pending"}
    record = parse_ornate_bill(raw)
    assert record.bill_id == "B1"
    assert record.amount == 200.0

def test_valid_ornate_payment():
    raw = {"PayID": "PAY1", "BillID": "B1", "Amount": "200.0", "Mode": "RTGS", "Reference": "UTR456", "PayDate": "2026-05-06"}
    record = parse_ornate_payment(raw)
    assert record.payment_id == "PAY1"
    assert record.utr_reference == "UTR456"

def test_valid_ornate_cheque():
    raw = {"ID": "C1", "BillID": "B1", "Number": "000222", "Bank": "HDFC", "Amount": "200.0", "Date": "2026-05-06", "Status": "Bounced"}
    record = parse_ornate_cheque(raw)
    assert record.cheque_id == "C1"
    assert record.amount == 200.0

def test_missing_required_field():
    raw = {"CustomerID": "O1", "FullName": "Bob"} # missing MobileNo and CityName
    with pytest.raises(KeyError):
        parse_ornate_customer(raw)

def test_malformed_erp_record():
    raw = {"PayID": "PAY1", "BillID": "B1", "Amount": "invalid_amount", "Mode": "RTGS", "Reference": "UTR456", "PayDate": "2026-05-06"}
    with pytest.raises(ValueError):
        parse_ornate_payment(raw)
