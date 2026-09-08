import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

class EmailValidator:
    """Validates normalized transaction data."""
    
    REQUIRED_FIELDS = ["amount", "mode", "utr", "transaction_date"]
    
    def validate(self, normalized_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Ensures all mandatory fields are present and valid.
        Returns (is_valid, list_of_errors).
        """
        errors = []
        
        # 1. Presence check
        for field in self.REQUIRED_FIELDS:
            if not normalized_data.get(field):
                errors.append(f"MISSING_FIELD: {field}")
        
        # 2. Logic check
        if normalized_data.get("amount", 0) <= 0:
            errors.append("INVALID_AMOUNT: Must be greater than 0")
            
        if normalized_data.get("mode") == "UNKNOWN":
            errors.append("UNKNOWN_MODE")
            
        if normalized_data.get("utr") and len(str(normalized_data["utr"])) < 8:
            errors.append("INVALID_UTR: Length too short")
            
        is_valid = len(errors) == 0
        
        if not is_valid:
            logger.warning(f"Validation failed for {normalized_data.get('utr')}: {errors}")
            
        return is_valid, errors
