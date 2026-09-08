from pydantic import BaseModel, Field
from typing import List, Dict

class ReconciliationDecision(BaseModel):
    status: str = Field(..., description="The status of the reconciliation decision.")
    reason: str = Field(..., description="The reason for the reconciliation decision.")
    risk_flags: List[str] = Field(..., description="List of risk flags associated with the decision.")
    requires_human_review: bool = Field(..., description="Flag indicating if human review is required.")

class ReconciliationInput(BaseModel):
    bills: List[Dict] = Field(..., description="List of bill records for reconciliation.")
    bank_alerts: List[Dict] = Field(..., description="List of bank alert records for reconciliation.")
    payments: List[Dict] = Field(..., description="List of payment records for reconciliation.")
    cheques: List[Dict] = Field(..., description="List of cheque records for reconciliation.")
