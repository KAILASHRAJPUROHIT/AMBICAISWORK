from pydantic import BaseModel, Field
from datetime import datetime
from typing import List

class ReconciliationDecision(BaseModel):
    status: str
    reason: str
    risk_flags: List[str]
    requires_human_review: bool
