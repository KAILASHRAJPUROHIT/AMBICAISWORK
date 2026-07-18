import base64
import json
import mimetypes
import os
import random
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, make_response, Response, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

import tenant_profile as tp

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'jobs.db'}")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024

db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
VALID_PRINT_MODES = {"pdf", "id_card"}


class PrintJob(db.Model):
    __tablename__ = "print_jobs"
    id = db.Column(db.String(32), primary_key=True)
    tenant_slug = db.Column(db.String(64), nullable=False, default="", index=True)
    status = db.Column(db.String(32), default="pending", nullable=False)
    print_mode = db.Column(db.String(32), default="pdf", nullable=False)
    copies = db.Column(db.Integer, default=1, nullable=False)
    file_paths = db.Column(db.Text, nullable=False, default="[]")
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


def init_db():
    with app.app_context():
        db.create_all()

        inspector = db.inspect(db.engine)
        columns = [col["name"] for col in inspector.get_columns("print_jobs")]

        with db.engine.connect() as conn:
            if "error_message" not in columns:
                conn.execute(db.text("ALTER TABLE print_jobs ADD COLUMN error_message TEXT"))
                conn.commit()
            if "tenant_slug" not in columns:
                conn.execute(db.text("ALTER TABLE print_jobs ADD COLUMN tenant_slug VARCHAR(64) DEFAULT ''"))
                conn.commit()

def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


# ── Document encryption at rest ───────────────────────────────────────────────
# Every tenant's uploaded documents are encrypted on disk with a per-tenant
# key (tenant_profile.default_profile's "encryption_key"). Decryption happens
# only in-memory, on the fly, when serving an authenticated request (customer
# admin view or the tenant's own print agent) — the plaintext is never
# written back to disk. This is separate from a tenant's "secure_documents"
# toggle, which additionally deletes the encrypted file the moment its job
# completes instead of keeping it for the normal 30-day retention window.

def _encrypt_bytes(data: bytes, profile: dict) -> bytes:
    key = (profile or {}).get("encryption_key")
    if not key:
        return data  # old/incomplete profile — degrade to unencrypted rather than break uploads
    return Fernet(key.encode()).encrypt(data)


def _decrypt_bytes(data: bytes, profile: dict) -> bytes:
    key = (profile or {}).get("encryption_key")
    if not key:
        return data
    try:
        return Fernet(key.encode()).decrypt(data)
    except InvalidToken:
        # Pre-encryption-feature files on disk are still plaintext — serve as-is.
        return data


def generate_queue_id(tenant_slug: str):
    prefix = "".join(c for c in tenant_slug.upper() if c.isalnum())[:3] or "AMB"
    today = datetime.now().strftime("%Y%m%d")
    for _ in range(1000):
        job_id = f"{prefix}-{today}-{random.randint(1, 999):03d}"
        if not PrintJob.query.get(job_id):
            return job_id
    raise RuntimeError("Unable to generate queue ID. Try again.")


# ── Multi-tenant binding ──────────────────────────────────────────────────────
# Every customer-facing/admin route needs to know which business it's serving.
# /api/agent/* routes are exempt — the local print agent authenticates via its
# own agent_api_key header instead (see get_pending_jobs), not the
# cookie/query-param flow customer browsers use.

TENANTS_DIR = tp.TENANTS_DIR
ACTIVE_SLUG = None
ACTIVE_PROFILE = None
UPLOAD_DIR = None
CHECKIN_DIR = None
HANDLES_FILE = None

_SETUP_EXEMPT_ROUTES = {"setup_page", "setup_save", "setup_logo", "setup_voice_clip", "static"}
_AGENT_EXEMPT_ROUTES = {"get_pending_jobs", "update_job_status"}


def _tenant_dir(slug: str) -> Path:
    d = Path(TENANTS_DIR) / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


@app.before_request
def _bind_tenant():
    global ACTIVE_SLUG, ACTIVE_PROFILE, UPLOAD_DIR, CHECKIN_DIR, HANDLES_FILE

    if request.endpoint in _SETUP_EXEMPT_ROUTES or request.endpoint in _AGENT_EXEMPT_ROUTES:
        return None

    slug = tp.resolve_active_slug(request)
    if not slug:
        if request.path.startswith("/api/") or request.path.startswith("/media/") or request.path.startswith("/checkin-photo/"):
            return jsonify({"error": "No tenant configured yet — visit /setup"}), 409
        return redirect(url_for("setup_page"))

    profile = tp.load_profile(slug)
    ACTIVE_SLUG, ACTIVE_PROFILE = slug, profile
    d = _tenant_dir(slug)
    UPLOAD_DIR = d / "uploads"
    UPLOAD_DIR.mkdir(exist_ok=True)
    CHECKIN_DIR = d / "checkins"
    CHECKIN_DIR.mkdir(exist_ok=True)
    HANDLES_FILE = d / "social_handles.csv"
    return None


# ── Setup wizard (exempt from tenant binding — see _SETUP_EXEMPT_ROUTES) ─────

@app.route("/setup", methods=["GET"])
def setup_page():
    tenants = tp.list_tenants()
    current_slug = request.args.get("tenant") or request.cookies.get("tenant_slug")
    edit_profile = tp.load_profile(current_slug) if current_slug else None
    return render_template("setup.html", tenants=tenants, edit_profile=edit_profile)


@app.route("/setup/save", methods=["POST"])
def setup_save():
    data = request.get_json(force=True) or {}
    business_name = (data.get("business_name") or "").strip()
    if not business_name:
        return jsonify({"ok": False, "error": "Business name is required"}), 400

    slug = data.get("slug") or tp.slugify(business_name)
    profile = tp.load_profile(slug) or tp.default_profile(business_name)
    profile["business_name"] = business_name
    profile["slug"] = slug
    profile["brand_colors"] = data.get("brand_colors") or profile.get("brand_colors")
    profile["instagram_handle"] = (data.get("instagram_handle") or "").strip()
    profile["facebook_page"] = (data.get("facebook_page") or "").strip()
    profile["google_review_url"] = (data.get("google_review_url") or "").strip()
    profile["whatsapp_number"] = (data.get("whatsapp_number") or "").strip()
    profile["phone_number"] = (data.get("phone_number") or "").strip()
    profile["secure_documents"] = bool(data.get("secure_documents"))

    tp.save_profile(profile)
    resp = jsonify({
        "ok": True, "slug": slug,
        "agent_api_key": profile["agent_api_key"],
        "admin_secret": profile["admin_secret"],
    })
    resp.set_cookie("tenant_slug", slug, max_age=60 * 60 * 24 * 365)
    return resp


@app.route("/setup/logo", methods=["POST"])
def setup_logo():
    slug = request.form.get("slug", "").strip()
    if not slug:
        return jsonify({"ok": False, "error": "Save the business name first"}), 400
    profile = tp.load_profile(slug)
    if not profile:
        return jsonify({"ok": False, "error": "Unknown tenant"}), 404

    logo_file = request.files.get("logo")
    if not logo_file or not logo_file.filename:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    ext = Path(logo_file.filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        return jsonify({"ok": False, "error": "Logo must be PNG or JPG"}), 400

    tenant_dir = _tenant_dir(slug)
    logo_dest = tenant_dir / f"logo{ext}"
    logo_file.save(logo_dest)
    profile["logo_path"] = str(logo_dest)
    tp.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/setup/voice_clip", methods=["POST"])
def setup_voice_clip():
    slug = request.form.get("slug", "").strip()
    if not slug:
        return jsonify({"ok": False, "error": "Save the business name first"}), 400
    profile = tp.load_profile(slug)
    if not profile:
        return jsonify({"ok": False, "error": "Unknown tenant"}), 404

    clip_file = request.files.get("voice_clip")
    if not clip_file or not clip_file.filename:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    ext = Path(clip_file.filename).suffix.lower()
    if ext not in (".mp3", ".wav", ".ogg", ".m4a"):
        return jsonify({"ok": False, "error": "Voice clip must be mp3/wav/ogg/m4a"}), 400

    tenant_dir = _tenant_dir(slug)
    clip_dest = tenant_dir / f"voice_clip{ext}"
    clip_file.save(clip_dest)
    profile["voice_clip_path"] = str(clip_dest)
    tp.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/setup/logo/<slug>", methods=["GET"])
def setup_logo_serve(slug):
    profile = tp.load_profile(slug)
    if not profile or not profile.get("logo_path"):
        return "", 404
    p = Path(profile["logo_path"])
    return send_from_directory(p.parent, p.name)


@app.route("/setup/voice_clip/<slug>", methods=["GET"])
def setup_voice_clip_serve(slug):
    profile = tp.load_profile(slug)
    if not profile or not profile.get("voice_clip_path"):
        return "", 404
    p = Path(profile["voice_clip_path"])
    return send_from_directory(p.parent, p.name)


@app.route("/", methods=["GET"])
def index():
    resp = make_response(render_template("index.html", profile=ACTIVE_PROFILE))
    resp.set_cookie("tenant_slug", ACTIVE_SLUG, max_age=60 * 60 * 24 * 365)
    return resp


@app.route("/print", methods=["GET"])
def print_page():
    production_mode = os.environ.get("PRODUCTION_MODE", "false").lower() == "true"
    resp = make_response(render_template("upload.html", production_mode=production_mode, profile=ACTIVE_PROFILE))
    resp.set_cookie("tenant_slug", ACTIVE_SLUG, max_age=60 * 60 * 24 * 365)
    return resp


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

    job_id = generate_queue_id(ACTIVE_SLUG)
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_files = []

    for uploaded in files:
        if not uploaded or not uploaded.filename:
            continue
        if not allowed_file(uploaded.filename):
            return jsonify({"error": f"Unsupported file type: {uploaded.filename}"}), 400
        safe_name = secure_filename(uploaded.filename) or f"file_{len(saved_files)+1}"
        destination = job_dir / safe_name
        if destination.exists():
            destination = job_dir / f"{destination.stem}_{len(saved_files)+1}{destination.suffix}"
        destination.write_bytes(_encrypt_bytes(uploaded.read(), ACTIVE_PROFILE))
        saved_files.append(destination.name)

    if not saved_files:
        return jsonify({"error": "No valid files uploaded."}), 400

    job = PrintJob(id=job_id, tenant_slug=ACTIVE_SLUG, status="pending", print_mode=print_mode,
                   copies=copies, file_paths=json.dumps(saved_files))
    db.session.add(job)
    db.session.commit()
    return jsonify({"success": True, "queue_id": job_id, "status": job.status, "file_count": len(saved_files)})


@app.route("/api/job/<job_id>", methods=["GET"])
def get_job_status(job_id):
    job = PrintJob.query.filter_by(id=job_id, tenant_slug=ACTIVE_SLUG).first_or_404()
    position = None
    if job.status == "pending":
        ahead = PrintJob.query.filter(
            PrintJob.tenant_slug == ACTIVE_SLUG,
            PrintJob.status == "pending",
            PrintJob.created_at < job.created_at
        ).count()
        position = ahead + 1
    return jsonify({"job_id": job.id, "status": job.status, "queue_position": position, "updated_at": job.updated_at.isoformat()})


def _authenticate_agent():
    """Resolves which tenant a polling print agent belongs to from its
    X-Agent-Key header — this is the fix that stops one shop's agent from
    ever seeing another shop's print jobs (previously this endpoint had no
    auth at all and returned every tenant's pending jobs to any caller)."""
    agent_key = request.headers.get("X-Agent-Key") or request.args.get("agent_key", "")
    return tp.find_by_agent_key(agent_key)


@app.route("/api/agent/jobs/pending", methods=["GET"])
def get_pending_jobs():
    tenant = _authenticate_agent()
    if not tenant:
        return jsonify({"error": "Invalid or missing agent key"}), 401

    jobs = (PrintJob.query
            .filter_by(status="pending", tenant_slug=tenant["slug"])
            .order_by(PrintJob.created_at.asc()).limit(5).all())
    response = []
    for job in jobs:
        filenames = json.loads(job.file_paths or "[]")
        files = [{"filename": name, "url": request.url_root.rstrip("/") + f"/media/{job.id}/{name}?tenant={tenant['slug']}"} for name in filenames]
        response.append({"job_id": job.id, "status": job.status, "print_mode": job.print_mode, "copies": job.copies, "files": files, "created_at": job.created_at.isoformat()})
    return jsonify(response)


@app.route("/api/agent/jobs/<job_id>/status", methods=["POST", "PATCH"])
def update_job_status(job_id):
    tenant = _authenticate_agent()
    if not tenant:
        return jsonify({"error": "Invalid or missing agent key"}), 401

    job = PrintJob.query.filter_by(id=job_id, tenant_slug=tenant["slug"]).first_or_404()
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

    # Secure-documents tenants: don't wait for the 30-day cleanup sweep —
    # once the agent confirms printing, the customer's document is deleted
    # immediately rather than retained.
    if status == "completed" and tenant.get("secure_documents"):
        job_dir = _tenant_dir(tenant["slug"]) / "uploads" / secure_filename(job.id)
        shutil.rmtree(job_dir, ignore_errors=True)

    return jsonify({"success": True, "job_id": job.id, "status": job.status})


@app.route("/media/<job_id>/<path:filename>", methods=["GET"])
def media(job_id, filename):
    job = PrintJob.query.filter_by(id=job_id, tenant_slug=ACTIVE_SLUG).first_or_404()
    safe_name = secure_filename(filename)
    file_path = UPLOAD_DIR / secure_filename(job_id) / safe_name
    if not file_path.is_file():
        abort(404)
    data = _decrypt_bytes(file_path.read_bytes(), ACTIVE_PROFILE)
    mimetype = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return Response(
        data, mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


def _check_admin_secret(data: dict) -> bool:
    expected = (ACTIVE_PROFILE or {}).get("admin_secret", "")
    if not expected:
        return True  # tenant hasn't set one — no gate (matches old ADMIN_SECRET-unset behavior)
    return data.get("secret") == expected


@app.route("/admin", methods=["GET"])
def admin():
    jobs = (PrintJob.query.filter_by(tenant_slug=ACTIVE_SLUG)
            .order_by(PrintJob.created_at.desc()).limit(100).all())
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
    business_name = (ACTIVE_PROFILE or {}).get("business_name", "")
    return f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AMBIC SmartQR Admin</title>
<style>
*{{box-sizing:border-box}}body{{font-family:Arial,sans-serif;background:#0a0a14;color:#ddd;padding:16px;margin:0;max-width:600px;margin:0 auto}}
h1{{color:#D4AF37;font-family:Georgia,serif;font-size:22px;margin-bottom:4px}}
.sub{{color:#888;font-size:13px;margin-bottom:16px}}
.nav{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px}}
.nav a,.nav button{{padding:9px 14px;border-radius:6px;font-size:13px;font-weight:bold;text-decoration:none;border:none;cursor:pointer}}
</style>
<meta http-equiv="refresh" content="10">
</head><body>
<h1>🖨 AMBIC SmartQR — Print Queue</h1>
<div class="sub">{business_name}</div>
<div class="nav">
  <a href="/admin/history" style="background:#06142E;color:#D4AF37">📷 History</a>
  <a href="/admin/checkins" style="background:#1a0a2e;color:#D4AF37">👤 Staff</a>
  <a href="/admin/social-handles" style="background:#0a2e1a;color:#D4AF37">📱 Handles</a>
  <button onclick="clearPending()" style="background:#d9534f;color:white">🗑 Clear Pending</button>
</div>
<script>
function clearPending(){{const s=prompt("Admin Secret:");if(!s)return;fetch("/admin/clear-pending",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{secret:s}})}}).then(r=>r.json()).then(d=>{{if(d.error)alert(d.error);else{{alert("Deleted: "+d.deleted);location.reload();}}}});}}
function retryJob(id){{const s=prompt("Admin Secret:");if(!s)return;fetch("/admin/retry/"+id,{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{secret:s}})}}).then(r=>r.json()).then(d=>{{if(d.error)alert(d.error);else{{alert("Retrying…");location.reload();}}}});}}
function reprintJob(id){{const s=prompt("Admin Secret:");if(!s)return;fetch("/admin/reprint/"+id,{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{secret:s}})}}).then(r=>r.json()).then(d=>{{if(d.error)alert(d.error);else{{alert("Sent to print again!");location.reload();}}}});}}
</script>
{cards if cards else "<p style='color:#555'>No jobs yet.</p>"}
</body></html>"""


@app.route("/admin/retry/<job_id>", methods=["POST"])
def admin_retry_job(job_id):
    data = request.get_json(silent=True) or {}
    if not _check_admin_secret(data):
        return jsonify({"error": "Unauthorized"}), 401
    job = PrintJob.query.filter_by(id=job_id, tenant_slug=ACTIVE_SLUG).first_or_404()
    if job.status != "failed":
        return jsonify({"error": "Only failed jobs can be retried."}), 400
    job.status = "pending"
    job.error_message = None
    job.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "job_id": job.id})


@app.route("/admin/reprint/<job_id>", methods=["POST"])
def admin_reprint_job(job_id):
    data = request.get_json(silent=True) or {}
    if not _check_admin_secret(data):
        return jsonify({"error": "Unauthorized"}), 401
    job = PrintJob.query.filter_by(id=job_id, tenant_slug=ACTIVE_SLUG).first_or_404()
    job.status = "pending"
    job.error_message = None
    job.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "job_id": job.id})


@app.route("/admin/clear-pending", methods=["POST"])
def admin_clear_pending():
    data = request.get_json(silent=True) or {}
    if not _check_admin_secret(data):
        return jsonify({"error": "Unauthorized"}), 401

    deleted = PrintJob.query.filter_by(status="pending", tenant_slug=ACTIVE_SLUG).delete()
    db.session.commit()
    return jsonify({"deleted": deleted})


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
    """Delete upload directories for jobs older than 30 days, across every tenant."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    removed = 0
    with app.app_context():
        for slug in tp.list_tenants():
            tenant_upload_dir = _tenant_dir(slug) / "uploads"
            old_jobs = PrintJob.query.filter(
                PrintJob.tenant_slug == slug, PrintJob.created_at < cutoff
            ).all()
            for job in old_jobs:
                job_dir = tenant_upload_dir / job.id
                if job_dir.exists():
                    shutil.rmtree(job_dir, ignore_errors=True)
                    removed += 1
    if removed:
        print(f"[cleanup] Removed {removed} upload directories older than 30 days.")


@app.route("/admin/history", methods=["GET"])
def admin_history():
    cutoff = datetime.utcnow() - timedelta(days=30)
    jobs = (PrintJob.query
            .filter(PrintJob.tenant_slug == ACTIVE_SLUG, PrintJob.created_at >= cutoff)
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
            on_disk = (UPLOAD_DIR / secure_filename(job.id) / secure_filename(name)).is_file()
            if not on_disk:
                thumbs += f'<div style="display:inline-flex;flex-direction:column;align-items:center;justify-content:center;width:100px;height:100px;background:#1a1a2e;border:1px solid #444;border-radius:4px;color:#666;font-size:11px;text-align:center;padding:6px">🔒<br>Deleted<br>(secure)</div>'
            elif ext in IMAGE_EXTS:
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
<title>AMBIC SmartQR — Print History</title>
<style>
body{{font-family:Arial,sans-serif;background:#0a0a14;color:#ddd;padding:20px;margin:0}}
h1{{color:#D4AF37;font-family:Georgia,serif;letter-spacing:2px}}
.grid{{columns:1;column-gap:16px}}
@media(min-width:600px){{.grid{{columns:2}}}}
@media(min-width:900px){{.grid{{columns:3}}}}
a.back{{color:#D4AF37;text-decoration:none;font-size:14px;display:inline-block;margin-bottom:20px}}
</style></head><body>
<a class="back" href="/admin">← Back to Admin</a>
<h1>Print History — Last 30 Days</h1>
<p style="color:#888;font-size:13px;margin-bottom:20px">{len(jobs)} job(s) found</p>
<div class="grid">{cards if cards else "<p style='color:#666'>No print jobs in the last 30 days.</p>"}</div>
</body></html>"""


init_db()
cleanup_old_uploads()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
