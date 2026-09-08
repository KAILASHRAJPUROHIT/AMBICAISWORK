"""Structured field extraction from a photographed KYC document (Aadhaar,
PAN, or bank passbook/cheque) using the local qwen3-vl model.

Never blind-trust the extraction -- consistent with this system's core rule
that no uncertain data gets treated as confirmed. Every numeric identifier
field is regex-validated for structural correctness (NOT proof of accuracy);
anything null or structurally invalid is flagged needs_review=True so it
surfaces for a human to check/correct rather than being silently presented
as ready-to-copy.
"""
import base64
import json
import logging
import re

import requests

logger = logging.getLogger("KYC_OCR_Extraction")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3-vl:4b-instruct-q4_K_M"

FIELDS = ["name", "address", "document_number", "bank_name", "account_number", "branch", "ifsc_code"]

EXTRACTION_PROMPT = """You are extracting structured fields from a photo of an Indian ID/KYC document (Aadhaar, PAN, or bank passbook/cheque). Look ONLY at what is literally printed in the image. Do not guess or invent any value you cannot actually read.

Return ONLY a single JSON object, no other text, with exactly these keys:
{
  "name": string or null,
  "address": string or null,
  "document_number": string or null,
  "bank_name": string or null,
  "account_number": string or null,
  "branch": string or null,
  "ifsc_code": string or null
}

If a field is not visible in the image, set it to null. Do not fabricate."""

# Structural sanity checks only -- these confirm shape, never correctness.
_AADHAAR_RE = re.compile(r"^\d{12}$")
_PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def _validate_document_number(value: str) -> bool:
    normalized = (value or "").replace(" ", "").upper()
    return bool(_AADHAAR_RE.match(normalized) or _PAN_RE.match(normalized))


def _validate_ifsc(value: str) -> bool:
    return bool(_IFSC_RE.match((value or "").replace(" ", "").upper()))


class ExtractionError(Exception):
    pass


def extract_kyc_fields(image_bytes: bytes, timeout: float = 60.0) -> dict:
    """Runs OCR extraction on one document image.

    Returns a dict: {fields: {...}, needs_review: [field names], raw_model_output: str}
    Raises ExtractionError if the model call fails or returns unparseable JSON
    -- caller should treat that as "needs a human to handle this document
    entirely," not silently proceed with empty fields.
    """
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": MODEL,
        "prompt": EXTRACTION_PROMPT,
        "images": [img_b64],
        "stream": False,
        "format": "json",
        # The local Ollama installation may default vision requests to a 4,096
        # token context. A normal phone scan exceeds that before the OCR prompt
        # is even considered, producing a 400 instead of an extraction. This
        # applies only to the request and stays well below the model's declared
        # 262k context capacity.
        "options": {"temperature": 0.0, "num_ctx": 16384},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise ExtractionError(f"Model call failed: {exc}") from exc

    raw_response = resp.json().get("response", "")
    try:
        extracted = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Model did not return valid JSON: {exc}\nRaw: {raw_response[:500]}") from exc

    fields = {}
    needs_review = []
    for key in FIELDS:
        value = extracted.get(key)
        value = value.strip() if isinstance(value, str) else None
        fields[key] = value or None
        if not value:
            needs_review.append(key)

    if fields["document_number"] and not _validate_document_number(fields["document_number"]):
        needs_review.append("document_number")
        logger.warning(f"document_number failed format validation: {fields['document_number']!r}")

    if fields["ifsc_code"] and not _validate_ifsc(fields["ifsc_code"]):
        needs_review.append("ifsc_code")
        logger.warning(f"ifsc_code failed format validation: {fields['ifsc_code']!r}")

    return {
        "fields": fields,
        "needs_review": sorted(set(needs_review)),
        "raw_model_output": raw_response,
    }
