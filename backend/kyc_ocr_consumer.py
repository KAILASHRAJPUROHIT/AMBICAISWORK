"""Consumes pending KYC documents from the cloud QR print server: downloads
each, runs local OCR extraction, stores the result in Payment Auditor, and
reports status back to the cloud server. Fully separate from print-job
handling (that's the print agent's job on PC2, an entirely different
codebase/process) -- this only ever touches the isolated kyc_documents table
and routes on the cloud server.
"""
import os
import time
import logging
import threading
from datetime import datetime

import requests

from backend.database import SessionLocal
from backend.kyc_ocr_extraction import extract_kyc_fields, ExtractionError
from backend.kyc_ocr_warmup_poller import mark_ocr_completed
# store_kyc_extraction is imported lazily inside _process_one_document, not
# at module level -- review_api imports start_kyc_ocr_consumer from this
# file for startup wiring, so a top-level import here would be circular.

logger = logging.getLogger("KYC_OCR_Consumer")

QR_PRINT_SERVER_BASE_URL = os.environ.get(
    "QR_PRINT_SERVER_BASE_URL", "https://print.aradhanajewellers.com"
)
PENDING_URL = f"{QR_PRINT_SERVER_BASE_URL}/api/kyc-ocr/pending"

POLL_INTERVAL_SECONDS = 3.0

kyc_consumer_status = {
    "last_check": None,
    "last_processed_doc_id": None,
    "last_error": None,
    "is_running": False,
}
_status_lock = threading.Lock()


def _ocr_image_bytes(source: bytes, filename: str) -> bytes:
    """Convert a PDF's first page locally; image documents pass through.

    QR documents never need a cloud OCR service. A multi-page PDF remains one
    review item for now; the first page is extracted and low-confidence fields
    are still human-reviewable rather than invented.
    """
    if not filename.lower().endswith(".pdf"):
        return source
    try:
        import pymupdf
        pdf = pymupdf.open(stream=source, filetype="pdf")
        if pdf.page_count < 1:
            raise ExtractionError("PDF has no pages")
        image = pdf[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).tobytes("png")
        pdf.close()
        return image
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Could not render PDF for OCR: {exc}") from exc


def _update_status(**kwargs):
    with _status_lock:
        for key, value in kwargs.items():
            if key in kyc_consumer_status:
                kyc_consumer_status[key] = value


def _report_status(doc_id: str, status: str, error: str = None, customer_name: str = None):
    try:
        payload = {"status": status}
        if error:
            payload["error"] = error[:2000]
        if customer_name:
            payload["customer_name"] = customer_name[:130]
        requests.post(f"{QR_PRINT_SERVER_BASE_URL}/api/kyc-ocr/{doc_id}/status", json=payload, timeout=10)
    except Exception as exc:
        logger.warning(f"Failed to report status for {doc_id}: {exc}")


def _process_one_document(doc: dict):
    doc_id = doc["doc_id"]
    logger.info(f"Processing KYC document {doc_id}")
    _report_status(doc_id, "processing")

    try:
        img_resp = requests.get(doc["url"], timeout=30)
        img_resp.raise_for_status()
        image_bytes = img_resp.content
    except requests.exceptions.RequestException as exc:
        logger.error(f"Failed to download {doc_id}: {exc}")
        _report_status(doc_id, "failed", f"Download failed: {exc}")
        return

    try:
        result = extract_kyc_fields(_ocr_image_bytes(image_bytes, doc.get("filename", "")))
    except ExtractionError as exc:
        logger.error(f"Extraction failed for {doc_id}: {exc}")
        _report_status(doc_id, "failed", f"Extraction failed: {exc}")
        return
    finally:
        # One OCR attempt is done (success or failure) -- sleep the model
        # regardless, per policy: never hold GPU memory longer than needed.
        mark_ocr_completed()

    from backend.review_api import store_kyc_extraction

    db = SessionLocal()
    try:
        store_kyc_extraction(doc_id, result["fields"], result["needs_review"], db)
    finally:
        db.close()

    _report_status(doc_id, "completed", customer_name=result["fields"].get("name"))
    _update_status(last_processed_doc_id=doc_id)
    logger.info(f"Completed {doc_id} (needs_review: {result['needs_review']})")


def _check_and_process():
    _update_status(is_running=True, last_check=datetime.now().isoformat())
    try:
        resp = requests.get(PENDING_URL, timeout=10)
        resp.raise_for_status()
        documents = resp.json().get("documents", [])
        _update_status(last_error=None)
        for doc in documents:
            _process_one_document(doc)
    except Exception as exc:
        _update_status(last_error=str(exc))
        logger.warning(f"Pending-document poll failed: {exc}")
    finally:
        _update_status(is_running=False)


def start_kyc_ocr_consumer():
    def run():
        while True:
            _check_and_process()
            time.sleep(POLL_INTERVAL_SECONDS)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info("KYC-OCR document consumer thread started.")
