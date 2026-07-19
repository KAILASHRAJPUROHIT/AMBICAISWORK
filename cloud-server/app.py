import base64
import json
import os
import random
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

# ── Default printer targeting ────────────────────────────────────────────────
# printer_name is only ever set (via /admin/set-printer) to a value that has
# actually appeared in available_printers, which the agent itself reports
# from its own PC (see /api/agent/printers). The agent refuses to print at
# all if the name it's told to use doesn't match one of its own currently
# installed printers — see local-print-agent/agent.py's process_job.
PRINTER_CONFIG_FILE = BASE_DIR / "printer_config.json"


def load_printer_config() -> dict:
    if not PRINTER_CONFIG_FILE.exists():
        return {"printer_name": "", "available_printers": [], "printers_reported_at": None}
    with open(PRINTER_CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_printer_config(config: dict) -> None:
    tmp = PRINTER_CONFIG_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    os.replace(tmp, PRINTER_CONFIG_FILE)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'jobs.db'}")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024

db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
VALID_PRINT_MODES = {"pdf", "id_card"}


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


def init_db():
    with app.app_context():
        db.create_all()

        inspector = db.inspect(db.engine)
        columns = [col["name"] for col in inspector.get_columns("print_jobs")]

        with db.engine.connect() as conn:
            if "error_message" not in columns:
                conn.execute(db.text("ALTER TABLE print_jobs ADD COLUMN error_message TEXT"))
                conn.commit()

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
    return render_template("upload.html", production_mode=production_mode)


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

    if not saved_files:
        return jsonify({"error": "No valid files uploaded."}), 400

    job = PrintJob(id=job_id, status="pending", print_mode=print_mode, copies=copies, file_paths=json.dumps(saved_files))
    db.session.add(job)
    db.session.commit()
    return jsonify({"success": True, "queue_id": job_id, "status": job.status, "file_count": len(saved_files)})


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
    return send_from_directory(UPLOAD_DIR / secure_filename(job_id), filename, as_attachment=True)


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
    if printer_name and printer_name not in available:
        return jsonify({"error": "That printer isn't in the reported printer list. Make sure the print agent is running and has reported its printers."}), 400

    config["printer_name"] = printer_name  # "" clears it, deliberately allowed
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
    """Delete upload directories for jobs older than 30 days."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    with app.app_context():
        old_jobs = PrintJob.query.filter(PrintJob.created_at < cutoff).all()
        removed = 0
        for job in old_jobs:
            job_dir = UPLOAD_DIR / job.id
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)
                removed += 1
    if removed:
        print(f"[cleanup] Removed {removed} upload directories older than 30 days.")


@app.route("/admin/history", methods=["GET"])
def admin_history():
    cutoff = datetime.utcnow() - timedelta(days=30)
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
<h1>Print History — Last 30 Days</h1>
<p style="color:#888;font-size:13px;margin-bottom:20px">{len(jobs)} job(s) found</p>
<div class="grid">{cards if cards else "<p style='color:#666'>No print jobs in the last 30 days.</p>"}</div>
</body></html>"""


init_db()
cleanup_old_uploads()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
