"""Classifies each file in a QR document bundle as PAN / Aadhaar / Driving
License / etc, so the dashboard can show a real document type instead of a
raw filename like scan_1789190177917.jpg.

Standalone by design (only needs `requests`) - runs on whichever machine
already has Ollama + the vision model installed for KYC-OCR extraction, but
is otherwise independent of the payment-auditor package: it talks to the new
AWS payment-notifier service over HTTP, not the old local backend.

    NOTIFIER_URL=https://notifier.aradhanajewellers.com
    NOTIFIER_TOKEN=...   (same token the desktop popup uses)
    KYC_INGEST_TOKEN=... (same token the KYC-OCR consumer uses)

Run continuously (systemd/Task Scheduler) or as a one-shot via --once.
"""
import base64
import json
import logging
import os
import sys
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("DocumentTypeClassifier")

NOTIFIER_URL = os.environ.get("NOTIFIER_URL", "https://notifier.aradhanajewellers.com").rstrip("/")
NOTIFIER_TOKEN = os.environ.get("NOTIFIER_TOKEN", "")
KYC_INGEST_TOKEN = os.environ.get("KYC_INGEST_TOKEN", "")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.environ.get("KYC_OCR_MODEL", "qwen3-vl:4b-instruct-q4_K_M")

POLL_INTERVAL_SECONDS = float(os.environ.get("CLASSIFIER_POLL_INTERVAL_SECONDS", "10"))

DOCUMENT_TYPES = [
    "Aadhaar Card", "PAN Card", "Driving License", "Voter ID", "Passport",
    "Bank Passbook", "Cheque", "Other",
]

CLASSIFY_PROMPT = (
    "Look at this photo of an Indian ID/KYC document. Which ONE of these "
    "types is it: " + ", ".join(DOCUMENT_TYPES) + "? "
    "Reply with ONLY the exact type name from that list, nothing else."
)


class ClassificationError(Exception):
    pass


def classify_document_type(image_bytes: bytes, timeout: float = 60.0) -> str:
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": MODEL,
        "prompt": CLASSIFY_PROMPT,
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": 8192},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise ClassificationError(f"Model call failed: {exc}") from exc

    raw = resp.json().get("response", "").strip()
    # Model sometimes wraps the answer in a short sentence despite the
    # instruction - fall back to substring matching against the known list
    # rather than failing outright on anything not an exact match.
    for candidate in DOCUMENT_TYPES:
        if candidate.lower() in raw.lower():
            return candidate
    if not raw:
        raise ClassificationError("Model returned an empty response")
    return "Other"


def _headers(token: str) -> dict:
    return {"X-Notifier-Token": token} if token else {}


def _fetch_bundles() -> list:
    resp = requests.get(f"{NOTIFIER_URL}/api/documents", headers=_headers(NOTIFIER_TOKEN), timeout=15)
    resp.raise_for_status()
    return resp.json().get("documents", [])


def _download_file(bundle_id: str, filename: str) -> bytes:
    url = f"{NOTIFIER_URL}/api/documents/{bundle_id}/files/{filename}"
    resp = requests.get(url, headers=_headers(NOTIFIER_TOKEN), timeout=30)
    resp.raise_for_status()
    return resp.content


def _ingest_classification(bundle_id: str, filename: str, document_type: str) -> None:
    resp = requests.post(
        f"{NOTIFIER_URL}/api/documents/file-classification/ingest",
        headers={**_headers(KYC_INGEST_TOKEN), "Content-Type": "application/json"},
        json={"bundle_id": bundle_id, "filename": filename, "document_type": document_type},
        timeout=15,
    )
    resp.raise_for_status()


def _check_and_process() -> int:
    classified = 0
    try:
        bundles = _fetch_bundles()
    except requests.exceptions.RequestException as exc:
        logger.warning(f"Could not fetch document bundles: {exc}")
        return 0

    for bundle in bundles:
        bundle_id = bundle.get("bundle_id", "")
        for file_entry in bundle.get("files", []):
            filename = file_entry.get("filename") if isinstance(file_entry, dict) else file_entry
            already_typed = isinstance(file_entry, dict) and file_entry.get("document_type")
            if not filename or already_typed:
                continue
            if not filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                # PDFs and anything else aren't handled by this pass yet -
                # leave them unclassified rather than guessing.
                continue
            try:
                image_bytes = _download_file(bundle_id, filename)
                doc_type = classify_document_type(image_bytes)
                _ingest_classification(bundle_id, filename, doc_type)
                logger.info(f"Classified {bundle_id}/{filename} as {doc_type}")
                classified += 1
            except (requests.exceptions.RequestException, ClassificationError) as exc:
                logger.warning(f"Failed to classify {bundle_id}/{filename}: {exc}")
    return classified


def main():
    if not NOTIFIER_TOKEN or not KYC_INGEST_TOKEN:
        logger.critical("NOTIFIER_TOKEN and KYC_INGEST_TOKEN must both be set.")
        sys.exit(1)

    once = "--once" in sys.argv
    while True:
        count = _check_and_process()
        if count:
            logger.info(f"Classified {count} file(s) this pass.")
        if once:
            break
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
