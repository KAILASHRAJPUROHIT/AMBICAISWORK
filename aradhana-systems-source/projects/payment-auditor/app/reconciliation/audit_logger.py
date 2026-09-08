import json
import os
from datetime import datetime

class AuditLogger:
    """Handles immutable audit logging for reconciliation events."""
    
    def __init__(self, log_dir="C:/Aradhana/AuditLogs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

    def log_event(self, invoice_no, event_type, details):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "invoice_no": invoice_no,
            "event_type": event_type,
            "details": details
        }
        
        filename = f"{invoice_no.replace('/', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        log_path = os.path.join(self.log_dir, filename)
        
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, indent=4)
            
        return log_path
