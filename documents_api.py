# Documents tab: two independent data sources under one router.
#   1. Document bridge - a thin proxy to the QR print server's own
#      /api/document-bundles/* routes (already live on AWS separately).
#      This service never stores document data itself.
#   2. KYC-OCR results - ported from payment-auditor/backend/review_api.py's
#      store_kyc_extraction()/get_open_kyc_documents()/record_kyc_field_copy(),
#      same SystemSetting key/value pattern already used for bank-activity
#      copy-state. The OCR extraction itself (a local vision-language model
#      via Ollama) stays wherever it already runs - it's not portable to a
#      small shared AWS box - so this only exposes an ingest endpoint for
#      that local consumer to push its results to, replacing the old
#      in-process function call.
import hashlib
import json
import os
import re
from datetime import datetime
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog, SystemSetting

router = APIRouter()

NOTIFIER_TOKEN = os.environ.get("NOTIFIER_TOKEN", "")
KYC_INGEST_TOKEN = os.environ.get("KYC_INGEST_TOKEN", "")
QR_DOCUMENT_SERVER_URL = os.environ.get("QR_DOCUMENT_SERVER_URL", "https://print.aradhanajewellers.com").rstrip("/")
QR_DOCUMENT_BRIDGE_TOKEN = os.environ.get("QR_DOCUMENT_BRIDGE_TOKEN", "")


def require_notifier_token(x_notifier_token: str = Header(default="")):
    if not NOTIFIER_TOKEN or x_notifier_token != NOTIFIER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing notifier token.")


def require_kyc_ingest_token(x_kyc_ingest_token: str = Header(default="")):
    if not KYC_INGEST_TOKEN or x_kyc_ingest_token != KYC_INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing KYC ingest token.")


def _bank_activity_copy_colour(count: int) -> str:
    return "red" if count >= 2 else "green" if count == 1 else "blue"


# --- Document bridge (proxy to the QR print server) --------------------
def _qr_document_request(path: str, method: str = "GET", payload: Optional[dict] = None) -> tuple[bytes, str]:
    if not QR_DOCUMENT_BRIDGE_TOKEN:
        raise HTTPException(status_code=503, detail="Document bridge is not configured on this server.")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"X-Document-Bridge-Token": QR_DOCUMENT_BRIDGE_TOKEN}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = UrlRequest(QR_DOCUMENT_SERVER_URL + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return response.read(), response.headers.get_content_type()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise HTTPException(status_code=error.code, detail=detail) from error
    except URLError as error:
        raise HTTPException(status_code=502, detail=f"Document server unavailable: {error.reason}") from error


def _valid_document_id(value: str) -> str:
    if not re.fullmatch(r"DOC-[A-Z0-9-]{4,64}", value or ""):
        raise HTTPException(status_code=400, detail="Invalid document bundle id.")
    return value


def _file_type_key(bundle_id: str, filename: str) -> str:
    return f"document_file_type:{hashlib.sha256(f'{bundle_id}:{filename}'.encode('utf-8')).hexdigest()}"


@router.get("/api/documents")
async def get_document_dashboard(db: Session = Depends(get_db), _auth=Depends(require_notifier_token)):
    """Proxies the QR server's bundle dashboard, then enriches each file with
    its classified document type (PAN/Aadhaar/Driving License/...) if the
    local OCR classifier has already tagged it - falls back to the raw
    filename for anything not yet classified, never blocks on it."""
    raw, _ = _qr_document_request("/api/document-bundles/dashboard")
    payload = json.loads(raw)
    for doc in payload.get("documents", []):
        bundle_id = doc.get("bundle_id", "")
        enriched = []
        for filename in doc.get("files", []):
            key = _file_type_key(bundle_id, filename)
            setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            doc_type = None
            if setting:
                try:
                    doc_type = json.loads(setting.value).get("type")
                except (TypeError, ValueError, json.JSONDecodeError):
                    doc_type = None
            enriched.append({"filename": filename, "document_type": doc_type})
        doc["files"] = enriched
    return JSONResponse(content=payload)


class DocumentFileClassificationInput(BaseModel):
    bundle_id: str
    filename: str
    document_type: str


@router.post("/api/documents/file-classification/ingest")
async def ingest_document_file_classification(payload: DocumentFileClassificationInput, db: Session = Depends(get_db), _auth=Depends(require_kyc_ingest_token)):
    """Called by the local OCR classifier (same machine/token as the KYC-OCR
    consumer) once it has determined one file's document type."""
    key = _file_type_key(payload.bundle_id, payload.filename)
    record = {"type": payload.document_type.strip()[:60], "classified_at": datetime.now().isoformat()}
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = json.dumps(record)
    else:
        db.add(SystemSetting(key=key, value=json.dumps(record)))
    db.commit()
    return {"status": "stored", "bundle_id": payload.bundle_id, "filename": payload.filename, "document_type": record["type"]}


@router.get("/api/documents/{bundle_id}/files/{filename}")
async def download_document_file(bundle_id: str, filename: str, request: Request, x_notifier_token: str = Header(default="")):
    # <a download> links can't attach custom headers, so this one route also
    # accepts the token as a query param. Every other route stays header-only.
    token = x_notifier_token or request.query_params.get("token", "")
    if not NOTIFIER_TOKEN or token != NOTIFIER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing notifier token.")
    _valid_document_id(bundle_id)
    if filename != os.path.basename(filename):
        raise HTTPException(status_code=400, detail="Invalid document filename.")
    raw, content_type = _qr_document_request(f"/document-media/{quote(bundle_id)}/{quote(filename)}")
    return Response(content=raw, media_type=content_type or "application/octet-stream",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/api/documents/{bundle_id}/reprint")
async def reprint_document(bundle_id: str, _auth=Depends(require_notifier_token)):
    _valid_document_id(bundle_id)
    raw, _ = _qr_document_request(f"/api/document-bundles/{quote(bundle_id)}/reprint", "POST", {})
    return JSONResponse(content=json.loads(raw))


@router.post("/api/documents/{bundle_id}/resend-to-biller")
async def resend_document_to_biller(bundle_id: str, _auth=Depends(require_notifier_token)):
    _valid_document_id(bundle_id)
    raw, _ = _qr_document_request(f"/api/document-bundles/{quote(bundle_id)}/resend-to-biller", "POST", {})
    return JSONResponse(content=json.loads(raw))


# --- KYC-OCR results -----------------------------------------------------
KYC_FIELD_LABELS = {
    "name": "Name",
    "address": "Address",
    "document_number": "Document Number",
    "bank_name": "Bank Name",
    "account_number": "Account Number",
    "branch": "Branch",
    "ifsc_code": "IFSC Code",
}


def _kyc_field_copy_key(doc_id: str, field: str) -> str:
    return f"kyc_field_copy_state:{hashlib.sha256(f'{doc_id}:{field}'.encode('utf-8')).hexdigest()}"


class KYCIngestInput(BaseModel):
    doc_id: str
    fields: dict
    needs_review: list = []


@router.post("/api/kyc-documents/ingest")
async def ingest_kyc_extraction(payload: KYCIngestInput, db: Session = Depends(get_db), _auth=Depends(require_kyc_ingest_token)):
    """Called by the local OCR consumer once extraction finishes for one
    document. Replaces the old in-process store_kyc_extraction() call —
    the consumer runs on a different machine now (wherever Ollama lives),
    not in this process."""
    record = {
        "doc_id": payload.doc_id,
        "fields": payload.fields,
        "needs_review": payload.needs_review,
        "extracted_at": datetime.now().isoformat(),
    }
    key = f"kyc_document:{payload.doc_id}"
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = json.dumps(record)
    else:
        db.add(SystemSetting(key=key, value=json.dumps(record)))
    db.add(AuditLog(
        entity_type="KYCDocument", entity_id=0, action="KYC_EXTRACTED",
        actor="LOCAL_KYC_OCR", metadata_json=json.dumps({"doc_id": payload.doc_id, "needs_review": payload.needs_review}),
    ))
    db.commit()
    return {"status": "stored", "doc_id": payload.doc_id}


@router.get("/api/kyc-documents/open")
async def get_open_kyc_documents(db: Session = Depends(get_db), _auth=Depends(require_notifier_token)):
    settings = (
        db.query(SystemSetting)
        .filter(SystemSetting.key.like("kyc_document:%"))
        .order_by(SystemSetting.key.desc())
        .limit(50)
        .all()
    )
    documents = []
    for setting in settings:
        try:
            record = json.loads(setting.value)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        doc_id = record.get("doc_id", "")
        field_rows = []
        for field_key, label in KYC_FIELD_LABELS.items():
            value = (record.get("fields") or {}).get(field_key)
            copy_key = _kyc_field_copy_key(doc_id, field_key)
            copy_setting = db.query(SystemSetting).filter(SystemSetting.key == copy_key).first()
            count = 0
            if copy_setting:
                try:
                    count = max(0, int(json.loads(copy_setting.value).get("count", 0)))
                except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                    count = 0
            field_rows.append({
                "field": field_key,
                "label": label,
                "value": value,
                "needs_review": field_key in (record.get("needs_review") or []),
                "copy_count": count,
                "copy_state": _bank_activity_copy_colour(count),
            })
        documents.append({
            "doc_id": doc_id,
            "extracted_at": record.get("extracted_at"),
            "fields": field_rows,
        })
    return JSONResponse(content={"documents": documents})


class KYCFieldCopiedInput(BaseModel):
    doc_id: str
    field: str
    source: str = "dashboard"


@router.post("/api/kyc-documents/field-copied")
async def record_kyc_field_copy(payload: KYCFieldCopiedInput, db: Session = Depends(get_db), _auth=Depends(require_notifier_token)):
    if payload.field not in KYC_FIELD_LABELS:
        raise HTTPException(status_code=400, detail="Unknown field.")
    key = _kyc_field_copy_key(payload.doc_id, payload.field)
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    previous_count = 0
    if setting:
        try:
            previous_count = max(0, int(json.loads(setting.value).get("count", 0)))
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            previous_count = 0
    count = previous_count + 1
    state = {"doc_id": payload.doc_id, "field": payload.field, "count": count, "last_copied_at": datetime.now().isoformat()}
    if setting:
        setting.value = json.dumps(state)
    else:
        db.add(SystemSetting(key=key, value=json.dumps(state)))
    db.add(AuditLog(
        entity_type="KYCField", entity_id=0, action="FIELD_COPIED", actor="LOCAL_KYC_OCR",
        metadata_json=json.dumps({"doc_id": payload.doc_id, "field": payload.field, "copy_count": count, "source": payload.source}),
    ))
    db.commit()
    return {"doc_id": payload.doc_id, "field": payload.field, "copy_count": count, "copy_state": _bank_activity_copy_colour(count)}
