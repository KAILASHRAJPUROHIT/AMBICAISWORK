import json
import os
import random
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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


@app.route("/api/agent/jobs/pending", methods=["GET"])
def get_pending_jobs():
    jobs = PrintJob.query.filter_by(status="pending").order_by(PrintJob.created_at.asc()).limit(5).all()
    response = []
    for job in jobs:
        filenames = json.loads(job.file_paths or "[]")
        files = [{"filename": name, "url": request.url_root.rstrip("/") + f"/media/{job.id}/{name}"} for name in filenames]
        response.append({"job_id": job.id, "status": job.status, "print_mode": job.print_mode, "copies": job.copies, "files": files, "created_at": job.created_at.isoformat()})
    return jsonify(response)


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
    rows = ""
    for job in jobs:
        file_count = len(json.loads(job.file_paths or "[]"))
        color = STATUS_COLOR.get(job.status, "#aaa")
        retry_btn = f'<button onclick="retryJob(\'{job.id}\')" style="padding:3px 10px;background:#e6a817;color:#000;border:none;border-radius:3px;cursor:pointer;font-size:12px;font-weight:bold">↺ Retry</button>' if job.status == "failed" else ""
        rows += f'<tr><td>{job.id}</td><td style="color:{color};font-weight:bold">{job.status}</td><td>{job.print_mode}</td><td>{job.copies}</td><td>{file_count}</td><td>{job.created_at.strftime("%d-%m-%Y %H:%M")}</td><td>{retry_btn}</td></tr>'
    return f"""<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Aradhana Print Admin</title><style>body{{font-family:Arial;background:#f7f5f0;padding:20px}}h1{{color:#06142E}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:10px;border-bottom:1px solid #ddd;font-size:14px}}th{{background:#06142E;color:#D4AF37;text-align:left}}</style><meta http-equiv="refresh" content="10"></head><body><h1>Aradhana Print Queue</h1><button onclick="clearPending()" style="margin-bottom:20px;padding:10px 15px;background:#d9534f;color:white;border:none;border-radius:4px;cursor:pointer;font-size:14px">[Clear Pending Queue]</button><script>function clearPending(){{const secret=prompt("Enter Admin Secret:");if(secret===null)return;fetch("/admin/clear-pending",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{secret:secret}})}}).then(r=>r.json()).then(data=>{{if(data.error)alert("Error: "+data.error);else{{alert("Deleted: "+data.deleted);location.reload();}}}}).catch(e=>alert("Request failed"));}}function retryJob(jobId){{const secret=prompt("Enter Admin Secret:");if(secret===null)return;fetch("/admin/retry/"+jobId,{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{secret:secret}})}}).then(r=>r.json()).then(data=>{{if(data.error)alert("Error: "+data.error);else{{alert("Job queued for retry");location.reload();}}}}).catch(e=>alert("Request failed"));}}</script><table><tr><th>Queue ID</th><th>Status</th><th>Mode</th><th>Copies</th><th>Files</th><th>Created</th><th>Actions</th></tr>{rows}</table></body></html>"""


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


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
