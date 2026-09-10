import base64
import json
import os
import random
import secrets
import hmac
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHECKIN_DIR = BASE_DIR / "checkins"
CHECKIN_DIR.mkdir(parents=True, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'jobs.db'}")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024

db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
VALID_PRINT_MODES = {"pdf", "id_card"}
DOCUMENT_RETENTION_DAYS = max(1, int(os.environ.get("QR_DOCUMENT_RETENTION_DAYS", "365")))
DOCUMENT_QUEUE_MINUTES = max(1, int(os.environ.get("QR_DOCUMENT_QUEUE_MINUTES", "30")))
# QR documents are never sent to an arbitrary desktop printer.
QR_REQUIRED_PRINTER = os.environ.get("QR_REQUIRED_PRINTER", "HP Laser MFP 355sdnw (05:32:A7)").strip()


class PrintJob(db.Model):
    __tablename__ = "print_jobs"
    id = db.Column(db.String(32), primary_key=True)
    status = db.Column(db.String(32), default="pending", nullable=False)
    print_mode = db.Column(db.String(32), default="pdf", nullable=False)
    copies = db.Column(db.Integer, default=1, nullable=False)
    file_paths = db.Column(db.Text, nullable=False, default="[]")
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ── Default printer targeting ────────────────────────────────────────────────
# Stored in the same SQLite database as everything else — not a standalone
# file — because a standalone file on disk is not reliably shared if this
# service ever runs as more than one instance/dyno (each gets its own local
# disk); the database is the one thing already proven consistent here.
# printer_name is only ever set (via /admin/set-printer) to a value that has
# actually appeared in available_printers, which the agent itself reports
# from its own PC (see /api/agent/printers). The agent refuses to print at
# all if the name it's told to use doesn't match one of its own currently
# installed printers — see local-print-agent/agent.py's process_job.
class PrinterConfig(db.Model):
    __tablename__ = "printer_config"
    id = db.Column(db.Integer, primary_key=True)
    printer_name = db.Column(db.String(255), nullable=False, default="")
    available_printers = db.Column(db.Text, nullable=False, default="[]")
    printers_reported_at = db.Column(db.DateTime, nullable=True)


def load_printer_config() -> dict:
    row = PrinterConfig.query.get(1)
    if not row:
        return {"printer_name": QR_REQUIRED_PRINTER, "available_printers": [], "printers_reported_at": None}
    return {
        "printer_name": QR_REQUIRED_PRINTER,
        "available_printers": json.loads(row.available_printers or "[]"),
        "printers_reported_at": row.printers_reported_at.isoformat() if row.printers_reported_at else None,
    }


def save_printer_config(config: dict) -> None:
    row = PrinterConfig.query.get(1)
    if not row:
        row = PrinterConfig(id=1)
        db.session.add(row)
    row.printer_name = config.get("printer_name", "") or ""
    row.available_printers = json.dumps(config.get("available_printers") or [])
    reported_at = config.get("printers_reported_at")
    if reported_at:
        row.printers_reported_at = (
            reported_at if isinstance(reported_at, datetime) else datetime.fromisoformat(reported_at)
        )
    db.session.commit()


# ── KYC document OCR (fully isolated from PrintJob / the printing pipeline) ─
# Deliberately a SEPARATE table and SEPARATE routes from PrintJob/upload/
# /api/agent/jobs/* -- the printing pipeline must never share a code path
# with this, so nothing here can ever regress printing.
KYC_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


class KYCDocument(db.Model):
    __tablename__ = "kyc_documents"
    id = db.Column(db.String(32), primary_key=True)
    status = db.Column(db.String(32), default="pending", nullable=False)  # pending, processing, completed, failed
    file_path = db.Column(db.String(255), nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# Delayed bill attachment. This is intentionally separate from PrintJob: a
# scanned ID may arrive before a bill exists, and must never auto-print.
class DocumentBundle(db.Model):
    __tablename__ = "document_bundles"
    id = db.Column(db.String(32), primary_key=True)
    display_name = db.Column(db.String(160), nullable=False)
    status = db.Column(db.String(32), default="pending", nullable=False)
    print_mode = db.Column(db.String(32), default="pdf", nullable=False)
    file_paths = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class DocumentBundleOcrLink(db.Model):
    """Maps an OCR work item to its held print bundle without mixing queues."""
    __tablename__ = "document_bundle_ocr_links"
    bundle_id = db.Column(db.String(32), db.ForeignKey("document_bundles.id"), primary_key=True)
    kyc_document_id = db.Column(db.String(32), db.ForeignKey("kyc_documents.id"), primary_key=True)


class DocumentScanSession(db.Model):
    __tablename__ = "document_scan_sessions"
    id = db.Column(db.String(32), primary_key=True)
    token = db.Column(db.String(96), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)


def _document_token_required():
    return os.environ.get("PRODUCTION_MODE", "false").lower() == "true"


def _valid_document_token(token):
    if not _document_token_required():
        return True
    session = DocumentScanSession.query.filter_by(token=token or "").first()
    return bool(session and not session.used_at and session.expires_at > datetime.utcnow())


def _document_bridge_authorized():
    """Allow document metadata/media only to the configured Router bridge."""
    expected = os.environ.get("DOCUMENT_BRIDGE_TOKEN", "")
    if not expected:
        # Never publish identity documents merely because deployment settings
        # were missed. The Router bridge is unavailable until configured.
        return False, ""
    supplied = request.headers.get("X-Document-Bridge-Token", "")
    return hmac.compare_digest(supplied, expected), ""


def _require_document_bridge():
    authorized, _ = _document_bridge_authorized()
    if authorized:
        return None
    if not os.environ.get("DOCUMENT_BRIDGE_TOKEN", ""):
        return jsonify({"error": "Document bridge is not configured."}), 503
    return jsonify({"error": "Unauthorized document bridge."}), 401


def _require_print_agent():
    """Restrict queue data and printable files to the enrolled local agent."""
    expected = os.environ.get("AGENT_TOKEN", "").strip()
    if not expected:
        if os.environ.get("PRODUCTION_MODE", "false").lower() == "true":
            return jsonify({"error": "Print agent is not configured."}), 503
        return None
    supplied = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not supplied.startswith(prefix) or not hmac.compare_digest(supplied[len(prefix):], expected):
        return jsonify({"error": "Unauthorized print agent."}), 401
    return None


@app.route("/api/document-scan-sessions", methods=["POST"])
def create_document_scan_session():
    secret = request.headers.get("X-Admin-Secret", "")
    expected = os.environ.get("ADMIN_SECRET", "")
    if not expected or not hmac.compare_digest(secret, expected):
        return jsonify({"error": "Unauthorized"}), 401
    scan_id, token = "SCAN-" + secrets.token_hex(6).upper(), secrets.token_urlsafe(32)
    db.session.add(DocumentScanSession(id=scan_id, token=token, expires_at=datetime.utcnow() + timedelta(minutes=15)))
    db.session.commit()
    return jsonify({"scan_id": scan_id, "token": token, "expires_in_seconds": 900}), 201


def _generate_document_bundle_id():
    today = datetime.now().strftime("%Y%m%d")
    for _ in range(1000):
        bundle_id = f"DOC-{today}-{random.randint(1, 999):03d}"
        if not DocumentBundle.query.get(bundle_id):
            return bundle_id
    raise RuntimeError("Unable to generate document bundle ID. Try again.")


def expire_document_bundles() -> int:
    """Remove unattended documents from the live queue, retaining archive data."""
    cutoff = datetime.utcnow() - timedelta(minutes=DOCUMENT_QUEUE_MINUTES)
    expired = DocumentBundle.query.filter(
        DocumentBundle.status == "pending", DocumentBundle.created_at < cutoff
    ).update({"status": "expired"}, synchronize_session=False)
    if expired:
        db.session.commit()
    return expired


def _enqueue_ocr_copy(source: Path, bundle_id: str | None = None) -> str | None:
    """Copy an image into the isolated local-OCR queue.

    Printing must remain independent: a copy/queue failure is deliberately not
    allowed to reject or delay a PrintJob.
    """
    if source.suffix.lower() not in KYC_ALLOWED_EXTENSIONS:
        return None
    doc_id = _generate_kyc_id()
    kyc_dir = UPLOAD_DIR / "kyc" / doc_id
    kyc_dir.mkdir(parents=True, exist_ok=True)
    target = kyc_dir / source.name
    shutil.copy2(source, target)
    db.session.add(KYCDocument(id=doc_id, status="pending", file_path=f"{doc_id}/{target.name}"))
    if bundle_id:
        db.session.add(DocumentBundleOcrLink(bundle_id=bundle_id, kyc_document_id=doc_id))
    return doc_id


def _create_pending_document_bundle(source_files: list[Path], display_name: str,
                                    print_mode: str) -> DocumentBundle:
    """Archive an attachable 30-minute bundle from already-validated files.

    Both QR actions use this: Direct to Printer remains an immediate P355 job,
    while the same scan is also eligible for a bill attachment until claimed
    or expired.  The archive copy isolates the attachment path from print-job
    cleanup and gives OCR one linked, durable source of truth.
    """
    bundle_id = _generate_document_bundle_id()
    bundle_dir = UPLOAD_DIR / "document-bundles" / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=False)
    saved_files: list[str] = []
    bundle = DocumentBundle(id=bundle_id, display_name=display_name[:160],
                            status="pending", print_mode=print_mode, file_paths="[]")
    db.session.add(bundle)
    try:
        for source in source_files:
            filename = secure_filename(source.name) or f"document_{len(saved_files) + 1}.jpg"
            destination = bundle_dir / filename
            if destination.exists():
                destination = bundle_dir / f"{destination.stem}_{len(saved_files) + 1}{destination.suffix}"
            shutil.copy2(source, destination)
            saved_files.append(destination.name)
            _enqueue_ocr_copy(destination, bundle_id)
        if not saved_files:
            raise ValueError("No valid files were available for the document bundle.")
        bundle.file_paths = json.dumps(saved_files)
        return bundle
    except Exception:
        shutil.rmtree(bundle_dir, ignore_errors=True)
        raise


@app.route("/api/document-bundles/upload", methods=["POST"])
def upload_document_bundle():
    """QR Scanner attachment mode. Creates a pending bundle and OCR items;
    does not touch the ordinary print queue.

    Accepts either a customer-facing scan-session token (the QR/browser flow)
    or the same low-privilege Router bridge token already used for the
    document read routes below -- lets a trusted internal client (e.g. the
    Ornate Buddy tablet app) upload directly without minting an admin-issued
    scan session, without ever needing the broader ADMIN_SECRET.
    """
    token = request.form.get("scan_token") or request.headers.get("X-Document-Scan-Token")
    bridge_authorized, _ = _document_bridge_authorized()
    if not bridge_authorized and not _valid_document_token(token):
        return jsonify({"error": "A valid scan session or Router bridge token is required."}), 401
    files = request.files.getlist("files[]") or request.files.getlist("files")
    display_name = (request.form.get("display_name") or "Pending ID documents").strip()
    print_mode = request.form.get("print_mode", "pdf").strip()
    if print_mode not in VALID_PRINT_MODES:
        return jsonify({"error": "Invalid print mode."}), 400
    if not files:
        return jsonify({"error": "No files selected."}), 400
    if len(files) > 12:
        return jsonify({"error": "Maximum 12 files allowed."}), 400
    bundle_id = _generate_document_bundle_id()
    bundle_dir = UPLOAD_DIR / "document-bundles" / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle = DocumentBundle(id=bundle_id, display_name=display_name[:160], status="pending",
                            print_mode=print_mode, file_paths="[]")
    db.session.add(bundle)
    saved = []
    for uploaded in files:
        if not uploaded or not uploaded.filename:
            continue
        if Path(uploaded.filename).suffix.lower() not in ALLOWED_EXTENSIONS:
            return jsonify({"error": f"Unsupported file type: {uploaded.filename}"}), 400
        filename = secure_filename(uploaded.filename) or f"document_{len(saved)+1}.jpg"
        destination = bundle_dir / filename
        if destination.exists():
            destination = bundle_dir / f"{destination.stem}_{len(saved)+1}{destination.suffix}"
        uploaded.save(destination)
        saved.append(destination.name)
        _enqueue_ocr_copy(destination, bundle_id)
    if not saved:
        return jsonify({"error": "No valid files uploaded."}), 400
    bundle.file_paths = json.dumps(saved)
    if _document_token_required():
        DocumentScanSession.query.filter_by(token=token).update({"used_at": datetime.utcnow()})
    db.session.commit()
    return jsonify({"success": True, "bundle_id": bundle_id, "status": "pending", "file_count": len(saved)})


@app.route("/api/document-bundles/pending", methods=["GET"])
def pending_document_bundles():
    denied = _require_document_bridge()
    if denied:
        return denied
    expire_document_bundles()
    bundles = DocumentBundle.query.filter_by(status="pending").order_by(DocumentBundle.created_at.desc()).limit(50).all()
    return jsonify({"bundles": [{
        "bundle_id": bundle.id,
        "display_name": bundle.display_name,
        "print_mode": bundle.print_mode,
        "file_count": len(json.loads(bundle.file_paths or "[]")),
        "created_at": bundle.created_at.isoformat(),
    } for bundle in bundles]})


@app.route("/api/document-bundles/<bundle_id>", methods=["GET"])
def get_document_bundle(bundle_id):
    denied = _require_document_bridge()
    if denied:
        return denied
    bundle = DocumentBundle.query.get_or_404(bundle_id)
    files = json.loads(bundle.file_paths or "[]")
    return jsonify({
        "bundle_id": bundle.id,
        "display_name": bundle.display_name,
        "status": bundle.status,
        "print_mode": bundle.print_mode,
        "files": [{"filename": name, "url": request.url_root.rstrip("/") + f"/document-media/{bundle.id}/{name}"} for name in files],
    })


@app.route("/api/document-bundles/<bundle_id>/print-standalone", methods=["POST"])
def print_document_bundle_standalone(bundle_id):
    """Explicitly queue one held bundle using the ordinary QR print agent.

    This route is bridge-authenticated and accepts only still-pending bundles,
    so an unattended document can never be printed or attached by accident.
    """
    denied = _require_document_bridge()
    if denied:
        return denied
    expire_document_bundles()
    bundle = DocumentBundle.query.get_or_404(bundle_id)
    if bundle.status != "pending":
        return jsonify({"error": "This document bundle is no longer pending.", "status": bundle.status}), 409
    return _queue_document_bundle(bundle, consume_pending=True)


@app.route("/api/document-bundles/<bundle_id>/claim-for-bill", methods=["POST"])
def claim_document_bundle_for_bill(bundle_id):
    """Atomically remove one confirmed bundle from all biller lists.

    The local router calls this only after it cached the selected documents.
    This makes the cloud queue authoritative across PC2 and Dell while never
    auto-attaching a document to a bill.
    """
    denied = _require_document_bridge()
    if denied:
        return denied
    expire_document_bundles()
    bundle = DocumentBundle.query.get_or_404(bundle_id)
    if bundle.status == "attached":
        return jsonify({"success": True, "bundle_id": bundle.id, "status": bundle.status, "existing": True})
    if bundle.status != "pending":
        return jsonify({"error": "This document bundle is no longer available for attachment.",
                        "status": bundle.status}), 409
    bundle.status = "attached"
    db.session.commit()
    return jsonify({"success": True, "bundle_id": bundle.id, "status": bundle.status})


def _queue_document_bundle(bundle: DocumentBundle, consume_pending: bool):
    """Create a 355-locked QR job from archived bundle files.

    The caller controls whether the held bundle is consumed. Dashboard reprint
    preserves its audit status; an explicit biller print consumes pending state.
    """
    filenames = json.loads(bundle.file_paths or "[]")
    if not filenames:
        return jsonify({"error": "This document bundle has no printable files."}), 409
    source_dir = UPLOAD_DIR / "document-bundles" / secure_filename(bundle.id)
    job_id = generate_queue_id()
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    copied = []
    try:
        for filename in filenames:
            safe_name = secure_filename(filename)
            source = source_dir / safe_name
            if not safe_name or not source.is_file():
                raise FileNotFoundError(filename)
            destination = job_dir / safe_name
            if destination.exists():
                destination = job_dir / f"{destination.stem}_{len(copied) + 1}{destination.suffix}"
            shutil.copy2(source, destination)
            copied.append(destination.name)
        job = PrintJob(id=job_id, status="pending", print_mode=bundle.print_mode, copies=1, file_paths=json.dumps(copied))
        db.session.add(job)
        if consume_pending:
            bundle.status = "standalone_queued"
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({"error": f"Could not queue document bundle: {error}"}), 409
    return jsonify({"success": True, "bundle_id": bundle.id, "queue_id": job_id,
                    "status": "pending", "file_count": len(copied)})


@app.route("/api/document-bundles/<bundle_id>/reprint", methods=["POST"])
def reprint_document_bundle(bundle_id):
    """Bridge-only historical reprint. It never alters biller-queue state."""
    denied = _require_document_bridge()
    if denied:
        return denied
    bundle = DocumentBundle.query.get_or_404(bundle_id)
    return _queue_document_bundle(bundle, consume_pending=False)


@app.route("/api/document-bundles/<bundle_id>/resend-to-biller", methods=["POST"])
def resend_document_bundle(bundle_id):
    """Create a fresh 30-minute held bundle from retained source files."""
    denied = _require_document_bridge()
    if denied:
        return denied
    source = DocumentBundle.query.get_or_404(bundle_id)
    filenames = json.loads(source.file_paths or "[]")
    if not filenames:
        return jsonify({"error": "This document bundle has no retained files."}), 409
    clone_id = _generate_document_bundle_id()
    clone = DocumentBundle(id=clone_id, display_name=source.display_name, status="pending",
                           print_mode=source.print_mode, file_paths=source.file_paths)
    db.session.add(clone)
    db.session.commit()
    return jsonify({"success": True, "bundle_id": clone_id, "status": "pending",
                    "expires_in_minutes": DOCUMENT_QUEUE_MINUTES})


@app.route("/api/document-bundles/dashboard", methods=["GET"])
def document_bundle_dashboard():
    """Bridge-only 365-day document index for the LAN dashboard."""
    denied = _require_document_bridge()
    if denied:
        return denied
    cutoff = datetime.utcnow() - timedelta(days=DOCUMENT_RETENTION_DAYS)
    bundles = (DocumentBundle.query.filter(DocumentBundle.created_at >= cutoff)
               .order_by(DocumentBundle.created_at.desc()).limit(500).all())
    return jsonify({"documents": [{
        "bundle_id": bundle.id,
        "customer_name": bundle.display_name,
        "document_type": "ID Cards" if bundle.print_mode == "id_card" else "Full Page",
        "document_count": len(json.loads(bundle.file_paths or "[]")),
        "status": bundle.status,
        "created_at": bundle.created_at.isoformat(),
        "files": json.loads(bundle.file_paths or "[]"),
    } for bundle in bundles]})


@app.route("/document-media/<bundle_id>/<path:filename>", methods=["GET"])
def document_bundle_media(bundle_id, filename):
    denied = _require_document_bridge()
    if denied:
        return denied
    return send_from_directory(UPLOAD_DIR / "document-bundles" / secure_filename(bundle_id), filename, as_attachment=True)


def _generate_kyc_id():
    today = datetime.now().strftime("%Y%m%d")
    for _ in range(1000):
        doc_id = f"KYC-{today}-{random.randint(1, 999):03d}"
        if not KYCDocument.query.get(doc_id):
            return doc_id
    raise RuntimeError("Unable to generate KYC document ID. Try again.")


@app.route("/api/kyc-ocr/upload", methods=["POST"])
def kyc_ocr_upload():
    """Separate from /upload (print jobs) on purpose -- this never touches
    PrintJob or the print queue at all."""
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "No file selected."}), 400
    if Path(uploaded.filename).suffix.lower() not in KYC_ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {uploaded.filename}"}), 400

    doc_id = _generate_kyc_id()
    doc_dir = UPLOAD_DIR / "kyc" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(uploaded.filename) or "document.jpg"
    destination = doc_dir / safe_name
    uploaded.save(destination)

    doc = KYCDocument(id=doc_id, status="pending", file_path=f"{doc_id}/{safe_name}")
    db.session.add(doc)
    db.session.commit()
    return jsonify({"success": True, "doc_id": doc_id, "status": doc.status})


@app.route("/api/kyc-ocr/pending", methods=["GET"])
def kyc_ocr_pending():
    """Polled by ARADHANA -- returns documents waiting for OCR."""
    docs = KYCDocument.query.filter_by(status="pending").order_by(KYCDocument.created_at.asc()).limit(5).all()
    response = [
        {
            "doc_id": d.id,
            # d.file_path is stored as "<doc_id>/<filename>" -- split back into
            # the two URL segments the route below actually expects.
            "url": request.url_root.rstrip("/") + f"/kyc-media/{d.file_path.split('/', 1)[0]}/{d.file_path.split('/', 1)[1]}",
            "created_at": d.created_at.isoformat(),
            "filename": Path(d.file_path).name,
        }
        for d in docs
    ]
    return jsonify({"documents": response})


@app.route("/api/kyc-ocr/backfill-print-jobs", methods=["POST"])
def backfill_print_job_ocr():
    """One controlled recovery path for QR jobs created before OCR queueing.

    It never creates a PrintJob or talks to an agent/printer. Re-run only when
    explicitly needed, since old jobs are intentionally re-queued for OCR.
    """
    denied = _require_document_bridge()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    try:
        minutes = int(data.get("minutes", 30))
    except (TypeError, ValueError):
        return jsonify({"error": "minutes must be an integer"}), 400
    minutes = max(1, min(minutes, 24 * 60))
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    queued = 0
    for job in PrintJob.query.filter(PrintJob.created_at >= cutoff).order_by(PrintJob.created_at.asc()).all():
        job_dir = UPLOAD_DIR / secure_filename(job.id)
        for filename in json.loads(job.file_paths or "[]"):
            source = job_dir / secure_filename(filename)
            if source.is_file() and _enqueue_ocr_copy(source):
                queued += 1
    db.session.commit()
    return jsonify({"success": True, "queued": queued, "window_minutes": minutes})


@app.route("/api/kyc-ocr/<doc_id>/status", methods=["POST", "PATCH"])
def kyc_ocr_update_status(doc_id):
    doc = KYCDocument.query.get_or_404(doc_id)
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"pending", "processing", "completed", "failed"}:
        return jsonify({"error": "Invalid status."}), 400
    doc.status = status
    doc.updated_at = datetime.utcnow()
    error_message = data.get("error") or data.get("error_message")
    if error_message:
        doc.error_message = str(error_message)[:2000]
    # OCR may label a pending bundle, but never establishes customer identity.
    # The visible suffix forces a biller to verify before attaching or printing.
    customer_name = str(data.get("customer_name") or "").strip()
    if status == "completed" and customer_name:
        label = f"{customer_name[:130]} — OCR name, verify"
        for link in DocumentBundleOcrLink.query.filter_by(kyc_document_id=doc.id).all():
            bundle = DocumentBundle.query.get(link.bundle_id)
            if bundle and bundle.status == "pending":
                bundle.display_name = label[:160]
    db.session.commit()
    return jsonify({"success": True, "doc_id": doc.id, "status": doc.status})


@app.route("/kyc-media/<doc_id>/<path:filename>", methods=["GET"])
def kyc_media(doc_id, filename):
    # Same safe pattern as the existing /media/<job_id>/<path:filename> route:
    # sanitize the (short, server-generated) doc_id segment, let
    # send_from_directory's own path-traversal protection handle filename.
    return send_from_directory(UPLOAD_DIR / "kyc" / secure_filename(doc_id), filename)


# ── KYC-OCR model warm-up signal ─────────────────────────────────────────────
# The local vision model that OCRs Aadhaar/PAN/bank documents (on ARADHANA,
# not this cloud server) stays unloaded from GPU memory by default -- a cold
# load takes ~80s, which a customer would feel as a frozen page. Rather than
# keeping it warm all day (wasting GPU memory the rest of the system also
# needs), ARADHANA polls this single timestamp at a fast interval and warms
# the model the moment a customer reaches the print page, well before they've
# actually selected/uploaded a document. Same row-1-only pattern as
# PrinterConfig above, for the same reason (works correctly even if this
# service ever runs as more than one instance).
class WarmupSignal(db.Model):
    __tablename__ = "warmup_signal"
    id = db.Column(db.Integer, primary_key=True)
    requested_at = db.Column(db.DateTime, nullable=True)


def init_db():
    with app.app_context():
        db.create_all()

        inspector = db.inspect(db.engine)
        columns = [col["name"] for col in inspector.get_columns("print_jobs")]
        bundle_columns = [col["name"] for col in inspector.get_columns("document_bundles")]

        with db.engine.connect() as conn:
            if "error_message" not in columns:
                conn.execute(db.text("ALTER TABLE print_jobs ADD COLUMN error_message TEXT"))
                conn.commit()
            if "print_mode" not in bundle_columns:
                conn.execute(db.text("ALTER TABLE document_bundles ADD COLUMN print_mode TEXT NOT NULL DEFAULT 'pdf'"))
                conn.commit()

        if not PrinterConfig.query.get(1):
            db.session.add(PrinterConfig(id=1, printer_name="", available_printers="[]"))
            db.session.commit()

        if not WarmupSignal.query.get(1):
            db.session.add(WarmupSignal(id=1, requested_at=None))
            db.session.commit()

def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def generate_queue_id():
    today = datetime.now().strftime("%Y%m%d")
    for _ in range(1000):
        job_id = f"AR-{today}-{random.randint(1, 999):03d}"
        if not PrintJob.query.get(job_id):
            return job_id
    raise RuntimeError("Unable to generate queue ID. Try again.")


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/print", methods=["GET"])
def print_page():
    production_mode = os.environ.get("PRODUCTION_MODE", "false").lower() == "true"
    _record_warmup_signal()
    return render_template("upload.html", production_mode=production_mode)


def _record_warmup_signal() -> None:
    """Best-effort -- a warm-up hint is never worth failing the actual page load over."""
    try:
        row = WarmupSignal.query.get(1)
        if not row:
            row = WarmupSignal(id=1)
            db.session.add(row)
        row.requested_at = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()


@app.route("/api/kyc-ocr/warmup-signal", methods=["GET"])
def get_kyc_ocr_warmup_signal():
    """Polled by ARADHANA (not by browsers) to decide whether to warm the
    local OCR model. Returns how many seconds ago a customer last reached
    /print, so the poller can apply its own freshness window without this
    endpoint needing to know that policy."""
    row = WarmupSignal.query.get(1)
    if not row or not row.requested_at:
        return jsonify({"requested_at": None, "seconds_ago": None})
    seconds_ago = (datetime.utcnow() - row.requested_at).total_seconds()
    return jsonify({"requested_at": row.requested_at.isoformat(), "seconds_ago": seconds_ago})


@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files[]") or request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files selected."}), 400
    if len(files) > 12:
        return jsonify({"error": "Maximum 12 files allowed."}), 400

    print_mode = request.form.get("print_mode", "pdf").strip()
    if print_mode not in VALID_PRINT_MODES:
        return jsonify({"error": "Invalid print mode."}), 400

    try:
        copies = int(request.form.get("copies", "1"))
    except ValueError:
        return jsonify({"error": "Invalid copies value."}), 400
    if copies < 1 or copies > 5:
        return jsonify({"error": "Copies must be between 1 and 5."}), 400

    job_id = generate_queue_id()
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_files = []
    saved_paths: list[Path] = []

    for uploaded in files:
        if not uploaded or not uploaded.filename:
            continue
        if not allowed_file(uploaded.filename):
            return jsonify({"error": f"Unsupported file type: {uploaded.filename}"}), 400
        safe_name = secure_filename(uploaded.filename) or f"file_{len(saved_files)+1}"
        destination = job_dir / safe_name
        if destination.exists():
            destination = job_dir / f"{destination.stem}_{len(saved_files)+1}{destination.suffix}"
        uploaded.save(destination)
        saved_files.append(destination.name)
        saved_paths.append(destination)

    if not saved_files:
        return jsonify({"error": "No valid files uploaded."}), 400

    # Direct printing and billing now share one document-record contract. The
    # PrintJob remains immediate and 355-only; this separate bundle merely
    # lets a biller attach the same recent scan within the 30-minute window.
    display_name = (request.form.get("display_name") or "Pending ID documents").strip()
    try:
        bundle = _create_pending_document_bundle(saved_paths, display_name, print_mode)
    except Exception as error:
        shutil.rmtree(job_dir, ignore_errors=True)
        db.session.rollback()
        return jsonify({"error": f"Could not retain this document for billing: {error}"}), 409

    job = PrintJob(id=job_id, status="pending", print_mode=print_mode, copies=copies, file_paths=json.dumps(saved_files))
    db.session.add(job)
    db.session.commit()
    return jsonify({"success": True, "queue_id": job_id, "attachment_bundle_id": bundle.id,
                    "status": job.status, "file_count": len(saved_files)})


@app.route("/api/job/<job_id>", methods=["GET"])
def get_job_status(job_id):
    job = PrintJob.query.get_or_404(job_id)
    position = None
    if job.status == "pending":
        ahead = PrintJob.query.filter(
            PrintJob.status == "pending",
            PrintJob.created_at < job.created_at
        ).count()
        position = ahead + 1
    return jsonify({"job_id": job.id, "status": job.status, "queue_position": position, "updated_at": job.updated_at.isoformat()})


@app.route("/api/agent/jobs/pending", methods=["GET"])
def get_pending_jobs():
    denied = _require_print_agent()
    if denied:
        return denied
    jobs = PrintJob.query.filter_by(status="pending").order_by(PrintJob.created_at.asc()).limit(5).all()
    response = []
    for job in jobs:
        filenames = json.loads(job.file_paths or "[]")
        files = [{"filename": name, "url": request.url_root.rstrip("/") + f"/media/{job.id}/{name}"} for name in filenames]
        response.append({"job_id": job.id, "status": job.status, "print_mode": job.print_mode, "copies": job.copies, "files": files, "created_at": job.created_at.isoformat()})
    # printer_name is the admin's selected default (see /admin/set-printer) —
    # the agent must not print anywhere else once this is set. An older
    # agent that only understands a bare list still works fine; it just
    # never looks at this key and falls back to its local .env value.
    printer_name = load_printer_config().get("printer_name") or ""
    return jsonify({"printer_name": printer_name, "jobs": response})


@app.route("/api/agent/printers", methods=["POST"])
def report_agent_printers():
    """The polling agent reports the Windows printers it can actually see on
    its own PC — this is what populates the dropdown in /admin so an owner
    picks from real, currently-installed printers instead of typing a name
    that might not match (the exact mismatch — "HP Laser MFP 330" vs
    "HP Laser MFP 355sdnw" — that caused real duplicate printing here)."""
    denied = _require_print_agent()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    printers = data.get("printers")
    if not isinstance(printers, list) or not all(isinstance(p, str) for p in printers):
        return jsonify({"error": "printers must be a list of strings"}), 400

    config = load_printer_config()
    config["available_printers"] = sorted(set(p.strip() for p in printers if p.strip()))
    config["printers_reported_at"] = datetime.utcnow().isoformat()
    save_printer_config(config)
    return jsonify({"ok": True, "count": len(config["available_printers"])})


@app.route("/api/agent/jobs/<job_id>/status", methods=["POST", "PATCH"])
def update_job_status(job_id):
    denied = _require_print_agent()
    if denied:
        return denied
    job = PrintJob.query.get_or_404(job_id)
    data = request.get_json(silent=True) or request.form
    status = data.get("status")
    if status not in {"pending", "printing", "completed", "failed"}:
        return jsonify({"error": "Invalid status."}), 400
    job.status = status
    job.updated_at = datetime.utcnow()
    error_message = data.get("error") or data.get("error_message")
    if error_message:
        job.error_message = str(error_message)[:2000]
    db.session.commit()
    return jsonify({"success": True, "job_id": job.id, "status": job.status})


@app.route("/media/<job_id>/<path:filename>", methods=["GET"])
def media(job_id, filename):
    denied = _require_print_agent()
    if denied:
        return denied
    return send_from_directory(UPLOAD_DIR / secure_filename(job_id), filename, as_attachment=True)


# LOCKED 2026-08-03 — verified working live at print.aradhanajewellers.com/dailyprice.
# Covered by test_dailyprice.py. Re-run that suite and re-check the live page
# before changing this route, gold_rate_renderer.py, or templates/dailyprice.html.
@app.route("/dailyprice", methods=["GET", "POST"])
def dailyprice():
    from gold_rate_renderer import RateImageRenderer, parse_rate

    error = None
    image_url = None
    if request.method == "POST":
        rate = parse_rate(request.form.get("rate", ""))
        if not rate:
            error = "Enter a valid rate, e.g. 135000"
        else:
            renderer = RateImageRenderer(
                BASE_DIR / "assets" / "gold_rate_template.png",
                BASE_DIR / "uploads" / "dailyprice",
                "Asia/Kolkata",
            )
            result = renderer.render(rate)
            image_url = f"/dailyprice/media/{result.path.name}"
    return render_template("dailyprice.html", error=error, image_url=image_url)


@app.route("/dailyprice/media/<path:filename>", methods=["GET"])
def dailyprice_media(filename):
    return send_from_directory(UPLOAD_DIR / "dailyprice", secure_filename(filename))


@app.route("/admin", methods=["GET"])
def admin():
    jobs = PrintJob.query.order_by(PrintJob.created_at.desc()).limit(100).all()
    STATUS_COLOR = {"pending": "#e6a817", "printing": "#5bc0de", "completed": "#5cb85c", "failed": "#d9534f"}
    cards = ""
    for job in jobs:
        file_count = len(json.loads(job.file_paths or "[]"))
        color = STATUS_COLOR.get(job.status, "#aaa")
        actions = ""
        if job.status == "failed":
            actions += f'<button onclick="retryJob(\'{job.id}\')" style="flex:1;padding:8px;background:#e6a817;color:#000;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:bold">↺ Retry</button>'
        if job.status in ("completed", "failed"):
            actions += f'<button onclick="reprintJob(\'{job.id}\')" style="flex:1;padding:8px;background:#5bc0de;color:#000;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:bold">🖨 Reprint</button>'
        actions_html = f'<div style="display:flex;gap:8px;margin-top:10px">{actions}</div>' if actions else ""
        error_html = f'<div style="font-size:11px;color:#d9534f;margin-top:6px;word-break:break-word">{job.error_message[:120]}…</div>' if job.error_message else ""
        cards += f'''<div style="background:#111;border:1px solid #222;border-radius:10px;padding:14px;margin-bottom:12px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                <span style="font-weight:bold;color:#D4AF37;font-size:15px;letter-spacing:1px">{job.id}</span>
                <span style="color:{color};font-size:12px;font-weight:bold;background:rgba(0,0,0,0.4);padding:3px 8px;border-radius:10px">{job.status.upper()}</span>
            </div>
            <div style="font-size:12px;color:#888">{job.created_at.strftime("%d %b %Y, %H:%M")} &nbsp;·&nbsp; {job.print_mode} &nbsp;·&nbsp; {job.copies}x &nbsp;·&nbsp; {file_count} file(s)</div>
            {error_html}{actions_html}
        </div>'''

    printer_config = load_printer_config()
    available_printers = printer_config.get("available_printers") or []
    current_printer = printer_config.get("printer_name") or ""
    if available_printers:
        options = '<option value="">— None selected —</option>' + "".join(
            f'<option value="{p}" {"selected" if p == current_printer else ""}>{p}</option>'
            for p in available_printers
        )
        status_line = (
            f'<div style="font-size:12px;color:#5cb85c;margin-top:8px">✓ Locked to "{current_printer}" — jobs will only print there.</div>'
            if current_printer else
            '<div style="font-size:12px;color:#e6a817;margin-top:8px">⚠ No default printer selected — the agent falls back to its local .env setting, if any.</div>'
        )
        printer_html = f'''<div style="background:#111;border:1px solid #222;border-radius:10px;padding:14px;margin-bottom:16px">
            <div style="font-weight:bold;color:#D4AF37;font-size:13px;margin-bottom:10px">🖨️ Default Printer</div>
            <select id="printerSelect" style="width:100%;padding:9px 10px;border-radius:6px;border:1px solid #333;background:#0a0a14;color:#ddd;font-size:13px;margin-bottom:8px">{options}</select>
            <button onclick="savePrinter()" style="width:100%;padding:9px;background:#D4AF37;color:#000;border:none;border-radius:6px;font-weight:bold;font-size:13px;cursor:pointer">Save Default Printer</button>
            {status_line}
            <div id="printerSaveMsg" style="font-size:12px;margin-top:6px"></div>
        </div>'''
    else:
        printer_html = '''<div style="background:#111;border:1px solid #222;border-radius:10px;padding:14px;margin-bottom:16px;font-size:12px;color:#888">
            🖨️ Waiting for the print agent to report its printers. Make sure it's running, then refresh this page.
        </div>'''

    return f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aradhana Print Admin</title>
<style>
*{{box-sizing:border-box}}body{{font-family:Arial,sans-serif;background:#0a0a14;color:#ddd;padding:16px;margin:0;max-width:600px;margin:0 auto}}
h1{{color:#D4AF37;font-family:Georgia,serif;font-size:22px;margin-bottom:16px}}
.nav{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px}}
.nav a,.nav button{{padding:9px 14px;border-radius:6px;font-size:13px;font-weight:bold;text-decoration:none;border:none;cursor:pointer}}
</style>
<meta http-equiv="refresh" content="10">
</head><body>
<h1>🖨 Print Queue</h1>
<div class="nav">
  <a href="/admin/history" style="background:#06142E;color:#D4AF37">📷 History</a>
  <a href="/admin/checkins" style="background:#1a0a2e;color:#D4AF37">👤 Staff</a>
  <a href="/admin/social-handles" style="background:#0a2e1a;color:#D4AF37">📱 Handles</a>
  <button onclick="clearPending()" style="background:#d9534f;color:white">🗑 Clear Pending</button>
</div>
{printer_html}
<script>
function clearPending(){{const s=prompt("Admin Secret:");if(!s)return;fetch("/admin/clear-pending",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{secret:s}})}}).then(r=>r.json()).then(d=>{{if(d.error)alert(d.error);else{{alert("Deleted: "+d.deleted);location.reload();}}}});}}
function retryJob(id){{const s=prompt("Admin Secret:");if(!s)return;fetch("/admin/retry/"+id,{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{secret:s}})}}).then(r=>r.json()).then(d=>{{if(d.error)alert(d.error);else{{alert("Retrying…");location.reload();}}}});}}
function reprintJob(id){{const s=prompt("Admin Secret:");if(!s)return;fetch("/admin/reprint/"+id,{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{secret:s}})}}).then(r=>r.json()).then(d=>{{if(d.error)alert(d.error);else{{alert("Sent to print again!");location.reload();}}}});}}
function savePrinter(){{
    const select=document.getElementById("printerSelect");
    const msg=document.getElementById("printerSaveMsg");
    if(!select)return;
    const s=prompt("Admin Secret (leave blank if none set):")||"";
    msg.textContent="Saving…";msg.style.color="#888";
    fetch("/admin/set-printer",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{printer_name:select.value,secret:s}})}})
        .then(r=>r.json())
        .then(d=>{{if(d.error){{msg.textContent="✗ "+d.error;msg.style.color="#d9534f";}}else{{location.reload();}}}})
        .catch(e=>{{msg.textContent="✗ Request failed: "+e;msg.style.color="#d9534f";}});
}}
</script>
{cards if cards else "<p style='color:#555'>No jobs yet.</p>"}
</body></html>"""


@app.route("/admin/retry/<job_id>", methods=["POST"])
def admin_retry_job(job_id):
    expected_secret = os.environ.get("ADMIN_SECRET")
    if expected_secret:
        data = request.get_json(silent=True) or {}
        if data.get("secret") != expected_secret:
            return jsonify({"error": "Unauthorized"}), 401
    job = PrintJob.query.get_or_404(job_id)
    if job.status != "failed":
        return jsonify({"error": "Only failed jobs can be retried."}), 400
    job.status = "pending"
    job.error_message = None
    job.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "job_id": job.id})


@app.route("/admin/reprint/<job_id>", methods=["POST"])
def admin_reprint_job(job_id):
    expected_secret = os.environ.get("ADMIN_SECRET")
    if expected_secret:
        data = request.get_json(silent=True) or {}
        if data.get("secret") != expected_secret:
            return jsonify({"error": "Unauthorized"}), 401
    job = PrintJob.query.get_or_404(job_id)
    job.status = "pending"
    job.error_message = None
    job.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "job_id": job.id})


@app.route("/admin/clear-pending", methods=["POST"])
def admin_clear_pending():
    expected_secret = os.environ.get("ADMIN_SECRET")
    if expected_secret:
        data = request.get_json(silent=True) or {}
        provided_secret = data.get("secret") or request.form.get("secret")
        if provided_secret != expected_secret:
            return jsonify({"error": "Unauthorized"}), 401
    
    deleted = PrintJob.query.filter_by(status="pending").delete()
    db.session.commit()
    return jsonify({"deleted": deleted})


@app.route("/admin/set-printer", methods=["POST"])
def admin_set_printer():
    expected_secret = os.environ.get("ADMIN_SECRET")
    data = request.get_json(silent=True) or {}
    if expected_secret:
        if data.get("secret") != expected_secret:
            return jsonify({"error": "Unauthorized"}), 401

    printer_name = (data.get("printer_name") or "").strip()
    config = load_printer_config()
    available = config.get("available_printers") or []
    if printer_name != QR_REQUIRED_PRINTER:
        return jsonify({"error": f"QR Print Server is locked to {QR_REQUIRED_PRINTER}."}), 400
    if printer_name not in available:
        return jsonify({"error": "The required 355 printer is not reported by the print agent."}), 400

    config["printer_name"] = QR_REQUIRED_PRINTER
    save_printer_config(config)
    return jsonify({"success": True, "printer_name": printer_name})


HANDLES_FILE = BASE_DIR / "social_handles.csv"


@app.route("/api/social-handle", methods=["POST"])
def save_social_handle():
    data = request.get_json(silent=True) or {}
    handle = (data.get("handle") or "").strip()[:60]
    if not handle:
        return jsonify({"error": "No handle"}), 400
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with open(HANDLES_FILE, "a", encoding="utf-8") as f:
        f.write(f'{ts},"{handle}"\n')
    return jsonify({"ok": True})


@app.route("/admin/social-handles", methods=["GET"])
def admin_social_handles():
    rows = ""
    entries = []
    if HANDLES_FILE.exists():
        for line in HANDLES_FILE.read_text(encoding="utf-8").splitlines():
            if "," not in line:
                continue
            ts, handle = line.split(",", 1)
            entries.append((ts.strip(), handle.strip().strip('"')))
    for ts, handle in reversed(entries):
        ig_url = f"https://www.instagram.com/{handle.lstrip('@').replace('@', '')}/"
        rows += f'<tr><td>{ts}</td><td><a href="{ig_url}" target="_blank" style="color:#D4AF37">{handle}</a></td></tr>'
    return f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Customer Handles</title>
<style>body{{font-family:Arial;background:#0a0a14;color:#ddd;padding:20px}}h1{{color:#D4AF37;font-family:Georgia,serif}}
table{{width:100%;border-collapse:collapse;background:#111}}th,td{{padding:10px 14px;border-bottom:1px solid #222;font-size:14px;text-align:left}}
th{{background:#06142E;color:#D4AF37}}a.back{{color:#D4AF37;text-decoration:none;font-size:14px;display:inline-block;margin-bottom:20px}}</style>
</head><body>
<a class="back" href="/admin">← Back to Admin</a>
<h1>Customer Instagram Handles</h1>
<p style="color:#888;font-size:13px;margin-bottom:16px">{len(entries)} collected</p>
<table><tr><th>Time (UTC)</th><th>Handle</th></tr>{rows if rows else "<tr><td colspan='2' style='color:#555'>None yet.</td></tr>"}</table>
</body></html>"""


@app.route("/api/checkin", methods=["POST"])
def staff_checkin():
    data = request.get_json(silent=True) or {}
    img_data = data.get("image", "")
    queue_id = data.get("queue_id", "unknown")
    if not img_data:
        return jsonify({"error": "No image"}), 400
    # Strip data URI prefix if present
    if "," in img_data:
        img_data = img_data.split(",", 1)[1]
    try:
        raw = base64.b64decode(img_data)
    except Exception:
        return jsonify({"error": "Invalid image data"}), 400
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{queue_id}.jpg"
    (CHECKIN_DIR / filename).write_bytes(raw)
    return jsonify({"ok": True})


@app.route("/checkin-photo/<filename>", methods=["GET"])
def checkin_photo(filename):
    return send_from_directory(CHECKIN_DIR, secure_filename(filename))


@app.route("/admin/checkins", methods=["GET"])
def admin_checkins():
    photos = sorted(CHECKIN_DIR.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
    cutoff = datetime.utcnow() - timedelta(days=30)
    cards = ""
    for photo in photos:
        mtime = datetime.utcfromtimestamp(photo.stat().st_mtime)
        if mtime < cutoff:
            continue
        parts = photo.stem.split("_", 3)
        try:
            ts_str = f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:]} {parts[1][:2]}:{parts[1][2:4]}:{parts[1][4:]}"
        except Exception:
            ts_str = photo.stem
        queue_id = "_".join(parts[2:]) if len(parts) > 2 else "—"
        img_url = f"/checkin-photo/{photo.name}"
        cards += f'''<div style="background:#111;border:1px solid #2a2a2a;border-radius:10px;overflow:hidden;break-inside:avoid;margin-bottom:16px">
            <img src="{img_url}" style="width:100%;display:block;object-fit:cover;max-height:260px">
            <div style="padding:10px 12px">
                <div style="color:#D4AF37;font-size:12px;font-weight:bold;margin-bottom:3px">{ts_str} UTC</div>
                <div style="color:#666;font-size:11px">Job: {queue_id}</div>
            </div>
        </div>'''
    return f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Staff Checkins</title>
<style>
body{{font-family:Arial,sans-serif;background:#0a0a14;color:#ddd;padding:20px;margin:0}}
h1{{color:#D4AF37;font-family:Georgia,serif;letter-spacing:2px}}
.grid{{columns:1;column-gap:16px}}
@media(min-width:500px){{.grid{{columns:2}}}}
@media(min-width:800px){{.grid{{columns:3}}}}
a.back{{color:#D4AF37;text-decoration:none;font-size:14px;display:inline-block;margin-bottom:20px}}
</style></head><body>
<a class="back" href="/admin">← Back to Admin</a>
<h1>Staff Activity — Last 30 Days</h1>
<p style="color:#888;font-size:13px;margin-bottom:20px">{len([p for p in photos if datetime.utcfromtimestamp(p.stat().st_mtime) >= cutoff])} photo(s)</p>
<div class="grid">{cards if cards else "<p style='color:#555'>No activity captured yet.</p>"}</div>
</body></html>"""


def cleanup_old_uploads():
    """Retain printable QR documents for the configured evidence period."""
    cutoff = datetime.utcnow() - timedelta(days=DOCUMENT_RETENTION_DAYS)
    with app.app_context():
        old_jobs = PrintJob.query.filter(PrintJob.created_at < cutoff).all()
        removed = 0
        for job in old_jobs:
            job_dir = UPLOAD_DIR / job.id
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)
                removed += 1
    if removed:
        print(f"[cleanup] Removed {removed} upload directories older than {DOCUMENT_RETENTION_DAYS} days.")


@app.route("/admin/history", methods=["GET"])
def admin_history():
    cutoff = datetime.utcnow() - timedelta(days=DOCUMENT_RETENTION_DAYS)
    jobs = (PrintJob.query
            .filter(PrintJob.created_at >= cutoff)
            .order_by(PrintJob.created_at.desc())
            .all())

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
    cards = ""
    for job in jobs:
        filenames = json.loads(job.file_paths or "[]")
        status_color = {"pending": "#e6a817", "printing": "#5bc0de", "completed": "#5cb85c", "failed": "#d9534f"}.get(job.status, "#aaa")
        thumbs = ""
        for name in filenames:
            ext = Path(name).suffix.lower()
            media_url = f"/media/{job.id}/{name}"
            if ext in IMAGE_EXTS:
                thumbs += f'<a href="{media_url}" target="_blank"><img src="{media_url}" style="width:100px;height:100px;object-fit:cover;border-radius:4px;border:1px solid #333;cursor:pointer" title="{name}"></a>'
            else:
                thumbs += f'<a href="{media_url}" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;width:100px;height:100px;background:#1a1a2e;border:1px solid #444;border-radius:4px;color:#D4AF37;font-size:11px;text-align:center;text-decoration:none;padding:6px">📄<br>{name[:20]}</a>'
        cards += f'''<div style="background:#111;border:1px solid #2a2a2a;border-radius:8px;padding:14px;break-inside:avoid;margin-bottom:16px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                <span style="font-weight:bold;color:#D4AF37;letter-spacing:1px">{job.id}</span>
                <span style="color:{status_color};font-size:12px;font-weight:bold">{job.status.upper()}</span>
            </div>
            <div style="font-size:11px;color:#888;margin-bottom:10px">{job.created_at.strftime("%d %b %Y, %H:%M")} &nbsp;·&nbsp; {job.print_mode} &nbsp;·&nbsp; {job.copies}x</div>
            <div style="display:flex;flex-wrap:wrap;gap:6px">{thumbs if thumbs else "<span style='color:#555;font-size:12px'>No files found on disk</span>"}</div>
        </div>'''

    return f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aradhana Print History</title>
<style>
body{{font-family:Arial,sans-serif;background:#0a0a14;color:#ddd;padding:20px;margin:0}}
h1{{color:#D4AF37;font-family:Georgia,serif;letter-spacing:2px}}
.grid{{columns:1;column-gap:16px}}
@media(min-width:600px){{.grid{{columns:2}}}}
@media(min-width:900px){{.grid{{columns:3}}}}
a.back{{color:#D4AF37;text-decoration:none;font-size:14px;display:inline-block;margin-bottom:20px}}
</style></head><body>
<a class="back" href="/admin">← Back to Admin</a>
<h1>Print History — Last {DOCUMENT_RETENTION_DAYS} Days</h1>
<p style="color:#888;font-size:13px;margin-bottom:20px">{len(jobs)} job(s) found</p>
<div class="grid">{cards if cards else "<p style='color:#666'>No print jobs in the last 30 days.</p>"}</div>
</body></html>"""


init_db()
cleanup_old_uploads()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
