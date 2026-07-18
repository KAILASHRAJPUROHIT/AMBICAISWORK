import base64
import hmac
import json
import mimetypes
import os
import random
import secrets
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, make_response, session, g, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import tenant_profile as tp

app = Flask(__name__)
# Required for the admin session cookie (see _admin_authenticated below) to
# be signed/tamper-proof. Falls back to a random per-process key so the app
# still runs without one set, but that invalidates every admin session on
# restart — set FLASK_SECRET_KEY in production so logins persist.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

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
    # Unauthenticated download token for /media/<job_id>/<filename>. The
    # queue_id alone (e.g. "SUN-20260717-042") is deliberately short and
    # human-readable for the customer to show at the counter — only 999
    # possible values per business per day, and easily scriptable to
    # enumerate. Document downloads require this separate, unguessable
    # token instead, which is only ever revealed to (a) the print agent
    # via its already-authenticated X-Agent-Key poll and (b) nowhere else.
    access_token = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class StaffUser(db.Model):
    """A named login for one person on one tenant's staff. Replaces the old
    single shared admin_secret (still supported as a legacy fallback for
    tenants that haven't created their first staff account yet — see
    _admin_authenticated) with real per-person accounts, so a shop can revoke
    one employee's access without changing a password everyone else shares,
    and actions are attributable to a person rather than "whoever had the
    secret". The first account ever created for a tenant is always "owner";
    only an owner can manage other accounts (see _require_owner)."""
    __tablename__ = "staff_users"
    id = db.Column(db.Integer, primary_key=True)
    tenant_slug = db.Column(db.String(64), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")  # "owner" or "staff"
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("tenant_slug", "email", name="uq_staff_tenant_email"),)


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
            if "access_token" not in columns:
                conn.execute(db.text("ALTER TABLE print_jobs ADD COLUMN access_token VARCHAR(64)"))
                conn.commit()

        # Backfill existing rows (from before this column existed) with a
        # real token instead of leaving them permanently inaccessible —
        # otherwise every in-flight job at deploy time would 403 forever.
        unset = PrintJob.query.filter(
            (PrintJob.access_token.is_(None)) | (PrintJob.access_token == "")
        ).all()
        for job in unset:
            job.access_token = secrets.token_urlsafe(32)
        if unset:
            db.session.commit()

def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


# ── Document encryption at rest ───────────────────────────────────────────────
# Every tenant's uploaded documents are encrypted on disk with a per-tenant
# key (tenant_profile.default_profile's "encryption_key"). Decryption happens
# only in-memory, on the fly, when serving an authenticated request (customer
# admin view or the tenant's own print agent) — the plaintext is never
# written back to disk. Retention itself (how long the encrypted file lives
# before deletion) is handled separately by document_retention_sweep below.

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

_SETUP_EXEMPT_ROUTES = {"setup_page", "setup_save", "setup_logo", "setup_voice_clip", "static"}
_AGENT_EXEMPT_ROUTES = {"get_pending_jobs", "update_job_status"}


def _tenant_dir(slug: str) -> Path:
    d = Path(TENANTS_DIR) / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


@app.before_request
def _bind_tenant():
    # Bound to flask.g (request-scoped), not module globals. The old code
    # rebound module-level ACTIVE_SLUG/ACTIVE_PROFILE/UPLOAD_DIR globals here
    # on every request — two tenants' requests running concurrently on
    # different worker threads shared that one mutable set, so one request
    # could read or write through another tenant's paths if their timing
    # overlapped. g is a fresh object per request; nothing left to race on.
    if request.endpoint in _SETUP_EXEMPT_ROUTES or request.endpoint in _AGENT_EXEMPT_ROUTES:
        return None

    slug = tp.resolve_active_slug(request)
    if not slug:
        if request.path.startswith("/api/") or request.path.startswith("/media/") or request.path.startswith("/checkin-photo/"):
            return jsonify({"error": "No tenant configured yet — visit /setup"}), 409
        return redirect(url_for("setup_page"))

    g.slug = slug
    g.profile = tp.load_profile(slug)
    d = _tenant_dir(slug)
    g.upload_dir = d / "uploads"
    g.upload_dir.mkdir(exist_ok=True)
    g.checkin_dir = d / "checkins"
    g.checkin_dir.mkdir(exist_ok=True)
    g.handles_file = d / "social_handles.csv"
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
    resp = make_response(render_template("index.html", profile=g.profile))
    resp.set_cookie("tenant_slug", g.slug, max_age=60 * 60 * 24 * 365)
    return resp


@app.route("/print", methods=["GET"])
def print_page():
    production_mode = os.environ.get("PRODUCTION_MODE", "false").lower() == "true"
    resp = make_response(render_template("upload.html", production_mode=production_mode, profile=g.profile))
    resp.set_cookie("tenant_slug", g.slug, max_age=60 * 60 * 24 * 365)
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

    job_id = generate_queue_id(g.slug)
    job_dir = g.upload_dir / job_id
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
        destination.write_bytes(_encrypt_bytes(uploaded.read(), g.profile))
        saved_files.append(destination.name)

    if not saved_files:
        return jsonify({"error": "No valid files uploaded."}), 400

    job = PrintJob(id=job_id, tenant_slug=g.slug, status="pending", print_mode=print_mode,
                   copies=copies, file_paths=json.dumps(saved_files),
                   access_token=secrets.token_urlsafe(32))
    db.session.add(job)
    db.session.commit()
    return jsonify({"success": True, "queue_id": job_id, "status": job.status, "file_count": len(saved_files)})


@app.route("/api/job/<job_id>", methods=["GET"])
def get_job_status(job_id):
    job = PrintJob.query.filter_by(id=job_id, tenant_slug=g.slug).first_or_404()
    position = None
    if job.status == "pending":
        ahead = PrintJob.query.filter(
            PrintJob.tenant_slug == g.slug,
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
        files = [{"filename": name, "url": request.url_root.rstrip("/") + f"/media/{job.id}/{name}?tenant={tenant['slug']}&token={job.access_token}"} for name in filenames]
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
    return jsonify({"success": True, "job_id": job.id, "status": job.status})


@app.route("/media/<job_id>/<path:filename>", methods=["GET"])
def media(job_id, filename):
    job = PrintJob.query.filter_by(id=job_id, tenant_slug=g.slug).first_or_404()
    # queue_id alone is not a secret — it's a 3-digit-per-day code shown to
    # the customer as their pickup reference, trivially enumerable. The
    # actual document download requires this separate, unguessable token
    # (see PrintJob.access_token), which only ever reaches the print agent
    # via its own X-Agent-Key-authenticated poll.
    token = request.args.get("token", "")
    if not job.access_token or not hmac.compare_digest(token, job.access_token):
        return jsonify({"error": "Invalid or missing access token"}), 403

    safe_name = secure_filename(filename)
    file_path = g.upload_dir / secure_filename(job_id) / safe_name
    if not file_path.is_file():
        return jsonify({"error": "File not found"}), 404
    data = _decrypt_bytes(file_path.read_bytes(), g.profile)
    mimetype = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return Response(
        data, mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


def _tenant_has_staff_users() -> bool:
    return StaffUser.query.filter_by(tenant_slug=g.slug).count() > 0


def _current_staff_user() -> StaffUser | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = StaffUser.query.get(user_id)
    if not user or user.tenant_slug != g.slug:
        return None
    return user


def _admin_authenticated() -> bool:
    """Session-based gate for every /admin* VIEW route. Every one of these
    used to be reachable with no auth at all — only the destructive POST
    actions (retry/reprint/clear-pending) ever checked a secret. /admin
    /history in particular renders full-resolution <img> thumbnails of
    every customer's uploaded document from the last 30 days directly on
    the page, so an unauthenticated GET there was a much bigger exposure
    than any single guessed job ID.

    Two auth paths: real per-person StaffUser accounts (preferred), or the
    legacy shared admin_secret for tenants that haven't created a staff
    account yet. Once a tenant has at least one StaffUser row the legacy
    secret path is retired for them — see admin_login."""
    if _tenant_has_staff_users():
        return _current_staff_user() is not None
    expected = (g.profile or {}).get("admin_secret", "")
    if not expected:
        return True  # tenant hasn't set a password — matches the existing behavior
    return session.get("admin_slug") == g.slug


def _current_role() -> str:
    """"owner" or "staff" for the authenticated session, or "" if
    unauthenticated. Legacy secret-authenticated sessions (pre-StaffUser
    tenants) are treated as owner — they hold the same secret an owner
    would set up their first real account with."""
    user = _current_staff_user()
    if user:
        return user.role
    if session.get("admin_slug") == g.slug:
        return "owner"
    return ""


def _require_admin():
    """Call at the top of every /admin* view. Returns a redirect to the
    login page (preserving where the visitor was headed) if not
    authenticated, otherwise None so the caller proceeds normally."""
    if not _admin_authenticated():
        return redirect(url_for("admin_login", next=request.path))
    return None


def _require_owner():
    """Call at the top of staff-management routes. Only an owner may add,
    remove, or view the list of staff accounts."""
    guard = _require_admin()
    if guard:
        return guard
    if _current_role() != "owner":
        return jsonify({"error": "Owner access required"}), 403
    return None


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    has_users = _tenant_has_staff_users()
    if request.method == "POST":
        if has_users:
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            user = StaffUser.query.filter_by(tenant_slug=g.slug, email=email).first()
            if user and check_password_hash(user.password_hash, password):
                session["user_id"] = user.id
                dest = request.args.get("next") or url_for("admin")
                return redirect(dest)
            error = "Incorrect email or password."
        else:
            expected = (g.profile or {}).get("admin_secret", "")
            if not expected or request.form.get("secret") == expected:
                session["admin_slug"] = g.slug
                dest = request.args.get("next") or url_for("admin")
                return redirect(dest)
            error = "Incorrect admin secret."
    business_name = (g.profile or {}).get("business_name", "")
    return render_template("admin_login.html", business_name=business_name, error=error,
                            has_users=has_users, profile=g.profile)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_slug", None)
    session.pop("user_id", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/users", methods=["GET"])
def admin_users():
    guard = _require_owner()
    if guard:
        return guard
    users = StaffUser.query.filter_by(tenant_slug=g.slug).order_by(StaffUser.created_at.asc()).all()
    business_name = (g.profile or {}).get("business_name", "")
    return render_template("admin_users.html", users=users, business_name=business_name,
                            current_user_id=session.get("user_id"), profile=g.profile)


@app.route("/admin/users/create", methods=["POST"])
def admin_users_create():
    # Bootstrapping the first account is allowed on the legacy secret alone
    # (no StaffUser rows exist yet, so _require_owner's admin check falls
    # through to the admin_secret session path); every account after that
    # requires an authenticated owner.
    guard = _require_owner()
    if guard:
        return guard
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role") if data.get("role") in ("owner", "staff") else "staff"
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if StaffUser.query.filter_by(tenant_slug=g.slug, email=email).first():
        return jsonify({"error": "That email already has an account"}), 400

    is_first = not _tenant_has_staff_users()
    user = StaffUser(tenant_slug=g.slug, email=email,
                      password_hash=generate_password_hash(password),
                      role="owner" if is_first else role)
    db.session.add(user)
    db.session.commit()
    return jsonify({"ok": True, "id": user.id, "role": user.role})


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
def admin_users_delete(user_id):
    guard = _require_owner()
    if guard:
        return guard
    user = StaffUser.query.filter_by(id=user_id, tenant_slug=g.slug).first_or_404()
    if user.id == session.get("user_id"):
        return jsonify({"error": "You can't remove your own account while logged in as it"}), 400
    if user.role == "owner":
        remaining_owners = StaffUser.query.filter_by(tenant_slug=g.slug, role="owner").count()
        if remaining_owners <= 1:
            return jsonify({"error": "Can't remove the last owner"}), 400
    db.session.delete(user)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/admin", methods=["GET"])
def admin():
    guard = _require_admin()
    if guard:
        return guard
    db_jobs = (PrintJob.query.filter_by(tenant_slug=g.slug)
               .order_by(PrintJob.created_at.desc()).limit(100).all())
    jobs = [{
        "id": job.id,
        "status": job.status,
        "print_mode": job.print_mode,
        "copies": job.copies,
        "error_message": job.error_message,
        "file_count": len(json.loads(job.file_paths or "[]")),
        "created_display": job.created_at.strftime("%d %b %Y, %H:%M"),
    } for job in db_jobs]
    business_name = (g.profile or {}).get("business_name", "")
    return render_template("admin.html", jobs=jobs, business_name=business_name, profile=g.profile,
                            is_owner=(_current_role() == "owner"),
                            legacy_secret_mode=(session.get("admin_slug") == g.slug))


@app.route("/admin/retry/<job_id>", methods=["POST"])
def admin_retry_job(job_id):
    # Gated on the logged-in admin session, not a per-action secret prompt —
    # once real per-person accounts exist there's no single shared secret to
    # prompt for, and re-entering it on every click was redundant with the
    # login the user already has.
    guard = _require_admin()
    if guard:
        return jsonify({"error": "Unauthorized"}), 401
    job = PrintJob.query.filter_by(id=job_id, tenant_slug=g.slug).first_or_404()
    if job.status != "failed":
        return jsonify({"error": "Only failed jobs can be retried."}), 400
    job.status = "pending"
    job.error_message = None
    job.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "job_id": job.id})


@app.route("/admin/reprint/<job_id>", methods=["POST"])
def admin_reprint_job(job_id):
    guard = _require_admin()
    if guard:
        return jsonify({"error": "Unauthorized"}), 401
    job = PrintJob.query.filter_by(id=job_id, tenant_slug=g.slug).first_or_404()
    job.status = "pending"
    job.error_message = None
    job.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "job_id": job.id})


@app.route("/admin/clear-pending", methods=["POST"])
def admin_clear_pending():
    guard = _require_admin()
    if guard:
        return jsonify({"error": "Unauthorized"}), 401

    deleted = PrintJob.query.filter_by(status="pending", tenant_slug=g.slug).delete()
    db.session.commit()
    return jsonify({"deleted": deleted})


@app.route("/api/social-handle", methods=["POST"])
def save_social_handle():
    data = request.get_json(silent=True) or {}
    handle = (data.get("handle") or "").strip()[:60]
    if not handle:
        return jsonify({"error": "No handle"}), 400
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with open(g.handles_file, "a", encoding="utf-8") as f:
        f.write(f'{ts},"{handle}"\n')
    return jsonify({"ok": True})


@app.route("/admin/social-handles", methods=["GET"])
def admin_social_handles():
    guard = _require_admin()
    if guard:
        return guard
    rows = ""
    entries = []
    if g.handles_file.exists():
        for line in g.handles_file.read_text(encoding="utf-8").splitlines():
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
    (g.checkin_dir / filename).write_bytes(raw)
    return jsonify({"ok": True})


@app.route("/checkin-photo/<filename>", methods=["GET"])
def checkin_photo(filename):
    # Only ever linked to from admin_checkins() below — no external agent
    # needs these the way the print agent needs /media files, so a session
    # check (rather than a separate token scheme) is enough here.
    guard = _require_admin()
    if guard:
        return guard
    return send_from_directory(g.checkin_dir, secure_filename(filename))


@app.route("/admin/checkins", methods=["GET"])
def admin_checkins():
    guard = _require_admin()
    if guard:
        return guard
    photos = sorted(g.checkin_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
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


# ── Document retention ────────────────────────────────────────────────────────
# This is the actual technical backing for "we don't keep your documents" —
# without it that's just marketing copy. A completed/failed job's files are
# only kept long enough for a same-visit admin reprint (paper jam, wrong
# tray, etc.), then deleted outright — not just made hard to reach. Jobs
# stuck pending/printing (customer walked off, agent never picked it up) get
# a longer safety-net window so nothing lingers forever on an edge case.
# cleanup_old_uploads() above only ever runs once at process start with a
# 30-day cutoff; this is the recurring, short-window sweep.
RETENTION_HOURS = float(os.environ.get("DOCUMENT_RETENTION_HOURS", "2"))
STALE_JOB_HOURS = float(os.environ.get("STALE_JOB_RETENTION_HOURS", "24"))
RETENTION_SWEEP_INTERVAL_SECONDS = 15 * 60


def _delete_job_files(job) -> bool:
    """Removes a job's uploaded files from disk and clears the DB references
    to them (file_paths, access_token) — the job row itself (id, status,
    timestamps) is kept for history/audit, only the document content goes."""
    if not job.file_paths or job.file_paths == "[]":
        return False
    job_dir = _tenant_dir(job.tenant_slug) / "uploads" / job.id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    job.file_paths = "[]"
    job.access_token = None
    return True


def document_retention_sweep():
    """One pass: delete files for jobs past their retention window. Called
    repeatedly by the background thread below, and safe to call more often
    than that if ever needed (e.g. manually) — it's just a query + delete,
    no state carried between calls."""
    now = datetime.utcnow()
    resolved_cutoff = now - timedelta(hours=RETENTION_HOURS)
    stale_cutoff = now - timedelta(hours=STALE_JOB_HOURS)
    cleaned = 0
    with app.app_context():
        resolved_jobs = PrintJob.query.filter(
            PrintJob.status.in_(("completed", "failed")),
            PrintJob.updated_at < resolved_cutoff,
        ).all()
        stale_jobs = PrintJob.query.filter(
            PrintJob.status.in_(("pending", "printing")),
            PrintJob.created_at < stale_cutoff,
        ).all()
        for job in resolved_jobs + stale_jobs:
            if _delete_job_files(job):
                cleaned += 1
        if cleaned:
            db.session.commit()
    if cleaned:
        print(f"[retention] Deleted documents for {cleaned} job(s) past their retention window.")


def _retention_sweep_loop():
    while True:
        try:
            document_retention_sweep()
        except Exception as e:
            print(f"[retention] Sweep failed (will retry next interval): {e}")
        time.sleep(RETENTION_SWEEP_INTERVAL_SECONDS)


def start_retention_sweep_thread():
    threading.Thread(target=_retention_sweep_loop, daemon=True, name="document-retention-sweep").start()


@app.route("/admin/history", methods=["GET"])
def admin_history():
    guard = _require_admin()
    if guard:
        return guard
    cutoff = datetime.utcnow() - timedelta(days=30)
    jobs = (PrintJob.query
            .filter(PrintJob.tenant_slug == g.slug, PrintJob.created_at >= cutoff)
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
            media_url = f"/media/{job.id}/{name}?token={job.access_token or ''}"
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
start_retention_sweep_thread()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
