"""AMBIC Jewellery Catalogue V2: Azure-only catalogue production UI."""

from __future__ import annotations

import glob
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path
from urllib.parse import quote

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for
import win32crypt

import email_2fa
import background_library
import stock_category_map
import stock_watcher
import ornament_code_map
import prompt_governance
import routing_preview
import paths
import dashboard_stats
import stock_excel
import category_dashboard
import capture_tool


BASE = Path(__file__).resolve().parent
INPUT = BASE / "input"
PROCESSING = BASE / "processing"
PROCESSED = BASE / "processed"
OUTPUT = BASE / "output"
NEEDS_REVIEW = BASE / "needs_review"
REJECTED = BASE / "rejected"
CAPTURE = BASE / "capture_intake"
BACKGROUNDS = BASE / "backgrounds"
BACKGROUNDS_DIR = str(BACKGROUNDS)
MODELS_DIR = str(BASE / "models")
REPORTS = BASE / "reports"
AZURE_REPORTS = REPORTS / "azure_flux2_guard"
CONFIG = BASE / "config" / "azure_flux2_guard.json"
DUPLICATE_GUARD_CONFIG = BASE / "config" / "duplicate_guard.json"
PROCESS_ENGINE = "azure_flux2_pro"


def _generated_password(env_var: str, filename: str) -> str:
    """Auth password: env var wins; otherwise a random value persisted under
    data/ (gitignored, same convention as _secret_key()). No hardcoded
    default — a forgotten env var must never fall back to a guessable
    literal password baked into source control."""
    value = os.environ.get(env_var)
    if value:
        return value
    path = BASE / "data" / filename
    if path.is_file() and path.read_text(encoding="utf-8").strip():
        return path.read_text(encoding="utf-8").strip()
    import secrets
    generated = secrets.token_urlsafe(18)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generated, encoding="utf-8")
    return generated


PROCESS_PASSWORD = _generated_password("AMBIC_PROCESS_PASSWORD", "process_password.txt")
ADMIN_PASSWORD = _generated_password("AMBIC_ADMIN_PASSWORD", "admin_password.txt")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
TYPES = sorted({
    "earrings", "ladies_rings", "gents_rings", "ladies_chains", "gents_chains",
    "ladies_bracelet", "gents_bracelet", "ladies_kada", "gents_kada", "locket",
    "pendant", "tops", "wati", "mangalsutra_short", "mangalsutra_long", "bangles",
    "ladies_bali", "mens_bali", "necklace", "silver", "diamond",
    *(category.key for category in stock_category_map.CATEGORIES),
})

for directory in (INPUT, PROCESSING, PROCESSED, OUTPUT, NEEDS_REVIEW, REJECTED, REPORTS):
    directory.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config.update(
    TEMPLATES_AUTO_RELOAD=True,
    MAX_CONTENT_LENGTH=250 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
)


def _secret_key() -> str:
    path = BASE / "data" / "flask_secret_key.txt"
    if path.is_file() and path.read_text(encoding="utf-8").strip():
        return path.read_text(encoding="utf-8").strip()
    import secrets
    value = secrets.token_hex(32)
    path.write_text(value, encoding="utf-8")
    return value


app.secret_key = _secret_key()
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 12

OTP_TTL_SECONDS = 10 * 60
OTP_MAX_ATTEMPTS = 5
PASSWORD_WINDOW_SECONDS = 15 * 60
PASSWORD_MAX_ATTEMPTS = 5
_password_failures: dict[str, list[float]] = {}
_password_failure_lock = threading.Lock()


def _client_key() -> str:
    forwarded = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",", 1)[0].strip() or request.remote_addr or "unknown")[:80]


def _password_limited(key: str) -> bool:
    cutoff = time.time() - PASSWORD_WINDOW_SECONDS
    with _password_failure_lock:
        recent = [stamp for stamp in _password_failures.get(key, []) if stamp >= cutoff]
        _password_failures[key] = recent
        return len(recent) >= PASSWORD_MAX_ATTEMPTS


def _record_password_failure(key: str) -> None:
    with _password_failure_lock:
        _password_failures.setdefault(key, []).append(time.time())


def _clear_password_failures(key: str) -> None:
    with _password_failure_lock:
        _password_failures.pop(key, None)


def _safe_next(value: str | None) -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("index")


def _otp_digest(salt: str, code: str) -> str:
    key = str(app.secret_key).encode("utf-8")
    return hmac.new(key, f"{salt}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def _two_factor_enabled() -> bool:
    """Email-OTP second factor: on by default. A persisted opt-out under
    data/ (gitignored, same convention as the password-override files)
    lets one install disable it without a code change, without touching
    the default for every other install of this tool."""
    env_value = os.environ.get("AMBIC_DISABLE_2FA")
    if env_value:
        return env_value.strip().lower() not in {"1", "true", "yes"}
    return not (BASE / "data" / "2fa_disabled.txt").is_file()


@app.before_request
def require_login():
    if request.path in {"/login", "/verify-otp", "/api/health"} or request.path.startswith("/static/"):
        return None
    if session.get("authed"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "not authenticated"}), 401
    return redirect(url_for("login", next=request.path))


@app.after_request
def no_stale_pages(response):
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        # Pragma/Expires are the HTTP/1.0-era complements to Cache-Control —
        # belt-and-suspenders against an intermediary proxy/cache that only
        # understands the older headers and would otherwise still be able
        # to serve a stale authenticated page.
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authed"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        key = _client_key()
        if _password_limited(key):
            return render_template("login.html", error="Too many attempts. Try again in 15 minutes."), 429
        if hmac.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            _clear_password_failures(key)
            if not _two_factor_enabled():
                destination = _safe_next(request.args.get("next"))
                session.clear()
                session.permanent = True
                session["authed"] = True
                session["auth_email"] = None
                session["authenticated_at"] = int(time.time())
                return redirect(destination)
            if not email_2fa.configured():
                return render_template("login.html", error="Email 2FA is not configured on this computer."), 503
            code = f"{secrets.randbelow(1_000_000):06d}"
            salt = secrets.token_hex(16)
            session.clear()
            session.permanent = False
            session["otp_hash"] = _otp_digest(salt, code)
            session["otp_salt"] = salt
            session["otp_expires"] = int(time.time()) + OTP_TTL_SECONDS
            session["otp_attempts"] = 0
            session["otp_next"] = _safe_next(request.args.get("next"))
            try:
                email_2fa.send_otp(code)
            except Exception:
                app.logger.exception("Could not send catalogue email OTP")
                session.clear()
                return render_template("login.html", error="Could not send the verification email."), 503
            return redirect(url_for("verify_otp"))
        _record_password_failure(key)
        error = "Wrong password"
    return render_template("login.html", error=error)


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if session.get("authed"):
        return redirect(url_for("index"))
    expected = session.get("otp_hash")
    salt = session.get("otp_salt")
    expires = int(session.get("otp_expires") or 0)
    if not expected or not salt:
        return redirect(url_for("login"))
    if time.time() > expires:
        session.clear()
        return render_template("login.html", error="Verification code expired. Sign in again."), 401

    error = None
    if request.method == "POST":
        attempts = int(session.get("otp_attempts") or 0) + 1
        session["otp_attempts"] = attempts
        if attempts > OTP_MAX_ATTEMPTS:
            session.clear()
            return render_template("login.html", error="Too many incorrect codes. Sign in again."), 429
        code = re.sub(r"\D", "", request.form.get("code", ""))
        if len(code) == 6 and hmac.compare_digest(_otp_digest(salt, code), expected):
            destination = session.get("otp_next") or url_for("index")
            session.clear()
            session.permanent = True
            session["authed"] = True
            session["auth_email"] = email_2fa.OTP_RECIPIENT
            session["authenticated_at"] = int(time.time())
            return redirect(_safe_next(destination))
        error = "Incorrect verification code"
    return render_template("verify_otp.html", error=error, email=email_2fa.OTP_RECIPIENT)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
def index():
    import raw_intake_sync
    captured = stock_category_map.captured_keys(
        raw_intake_sync.CAPTURE_INTAKE_SOURCE, raw_intake_sync.RAW_FINAL_DIR
    )
    needs_setup_keys = {c.key for c in stock_category_map.NEEDS_SETUP}
    categories = [
        {"key": c.key, "label": c.label, "disabled": c.key in needs_setup_keys and c.key not in captured}
        for c in stock_category_map.CATEGORIES
    ]
    return render_template("index.html", types=TYPES, categories=categories)


@app.get("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.get("/review")
def review_page():
    return render_template("review.html")


@app.get("/capture")
def capture_page():
    host = request.host.split(":")[0]
    return redirect(f"https://{host}:7660/capture")


def _images(root: Path, recursive: bool = False) -> list[Path]:
    iterator = root.rglob("*") if recursive else root.iterdir()
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda path: path.name.casefold(),
    ) if root.is_dir() else []


def _safe_child(root: Path, relative: str) -> Path | None:
    candidate = (root / relative).resolve()
    base = root.resolve()
    if candidate == base or base not in candidate.parents:
        return None
    return candidate


def _detect_upload_category(
    filenames: list[str], relative_paths: list[str], folder_name: str
) -> dict:
    """Resolve one authoritative category for a single-category batch.

    Folder paths and the latest daily stock workbook are independent signals.
    Any disagreement or mixed-category upload fails closed.
    """
    import stock_excel

    stock_map: dict[str, str] = {}
    stock_workbook = None
    stock_warning = None
    try:
        workbook = stock_watcher.current_workbook()
        stock_map = stock_excel.load_stock_label_categories(workbook)
        stock_workbook = workbook.name
    except Exception as exc:
        stock_warning = str(exc)

    detected: set[str] = set()
    evidence: list[dict] = []
    conflicts: list[str] = []
    for index, filename in enumerate(filenames):
        relative = relative_paths[index] if index < len(relative_paths) else filename
        path_value = relative if relative and relative != filename else f"{folder_name}/{filename}" if folder_name else filename
        path_category = stock_category_map.category_from_path(path_value)
        item_name = stock_map.get(Path(filename).stem.casefold())
        stock_category = stock_category_map.match_label(item_name.strip().casefold()) if item_name else None
        prefix_category = ornament_code_map.category_from_tag_code(Path(filename).stem)
        if stock_category and prefix_category and stock_category.key != prefix_category.key:
            conflicts.append(
                f"{filename}: tag prefix says {prefix_category.label}; stock says {stock_category.label}"
            )
            continue
        resolved_tag_category = stock_category or prefix_category
        if path_category and resolved_tag_category and path_category.key != resolved_tag_category.key:
            conflicts.append(
                f"{filename}: folder says {path_category.label}; "
                f"{'stock' if stock_category else 'tag prefix'} says {resolved_tag_category.label}"
            )
            continue
        category = resolved_tag_category or path_category
        if category:
            detected.add(category.key)
            evidence.append({
                "file": filename,
                "category": category.key,
                "label": category.label,
                "source": (
                    "folder + daily stock" if path_category and stock_category
                    else "daily stock" if stock_category
                    else "folder + tag prefix" if path_category and prefix_category
                    else "tag prefix" if prefix_category
                    else "folder path"
                ),
            })

    if conflicts:
        return {"error": "Category conflict: " + "; ".join(conflicts), "status": 409}
    if len(detected) > 1:
        labels = sorted({row["label"] for row in evidence})
        return {"error": "Mixed-category batch: " + ", ".join(labels), "status": 409}
    key = next(iter(detected), None)
    category = stock_category_map.BY_KEY.get(key) if key else None
    sources = sorted({row["source"] for row in evidence})
    return {
        "category": key,
        "label": category.label if category else None,
        "source": " + ".join(sources) if sources else None,
        "stock_workbook": stock_workbook,
        "stock_warning": stock_warning,
    }


@app.post("/api/upload")
def api_upload():
    uploads = request.files.getlist("files")
    filenames = [Path(upload.filename or "").name for upload in uploads]
    relative_paths = request.form.getlist("relative_paths")
    folder_name = re.sub(r'[/\\:*?"<>|]', "_", request.form.get("folder_name", "").strip())
    detection = _detect_upload_category(filenames, relative_paths, folder_name)
    if detection.get("error"):
        return jsonify({"error": detection["error"]}), int(detection["status"])
    for old in _images(INPUT):
        old.unlink(missing_ok=True)
    saved = 0
    for upload in uploads:
        name = Path(upload.filename or "").name
        if not name or Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        upload.save(INPUT / name)
        saved += 1
    session["batch_folder"] = folder_name or None
    session["detected_category"] = detection.get("category")
    session["category_detection"] = detection
    return jsonify({"saved": saved, "folder_name": folder_name or None, "detected_category": detection})


def _derive_single_items_from_disk() -> list[dict]:
    return [
        {"pair": index, "jewel": path.name, "tag": None, "label": path.stem, "folder": str(INPUT)}
        for index, path in enumerate(_images(INPUT), start=1)
    ]


@app.get("/api/load")
def api_load():
    pairs = _derive_single_items_from_disk()
    detection = session.get("category_detection") or {}
    if pairs and not detection.get("category"):
        filenames = [pair["jewel"] for pair in pairs]
        detection = _detect_upload_category(
            filenames,
            filenames,
            str(session.get("batch_folder") or ""),
        )
        if not detection.get("error"):
            session["detected_category"] = detection.get("category")
            session["category_detection"] = detection
    return jsonify({
        "count": len(pairs), "pairs": pairs, "mode": "ai_only", "unit": "items",
        "detected_category": detection,
    })


@app.get("/api/backgrounds")
def api_backgrounds():
    category = str(request.args.get("category") or "").strip()
    keywords = background_library.keywords_for_category(category)
    items = background_library.compatible_backgrounds(BACKGROUNDS, category)
    for item in items:
        item["url"] = "/img/backgrounds/" + "/".join(quote(part, safe="") for part in item["path"].split("/"))
    return jsonify({"category": category, "keywords": keywords, "count": len(items), "items": items})


@app.get("/api/stock/status")
def api_stock_status():
    return jsonify(stock_watcher.read_status())


def _clear_queue_session_if_empty() -> None:
    if _images(INPUT):
        return
    session["batch_folder"] = None
    session["detected_category"] = None
    session["category_detection"] = {}


@app.delete("/api/queue/item")
def api_queue_delete_item():
    if JOB.get("running"):
        return jsonify({"error": "Cannot change queue while processing"}), 409
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    if not name or Path(name).name != name or Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
        return jsonify({"error": "Invalid queue item"}), 400
    target = _safe_child(INPUT, name)
    if not target or not target.is_file():
        return jsonify({"error": "Queue item not found"}), 404
    target.unlink()
    _clear_queue_session_if_empty()
    return jsonify({"deleted": name, "remaining": len(_images(INPUT))})


@app.post("/api/queue/clear")
def api_queue_clear():
    if JOB.get("running"):
        return jsonify({"error": "Cannot change queue while processing"}), 409
    items = _images(INPUT)
    for path in items:
        path.unlink(missing_ok=True)
    _clear_queue_session_if_empty()
    return jsonify({"cleared": len(items), "remaining": 0})


@app.get("/img/<where>/<path:name>")
def serve_image(where: str, name: str):
    if where == "bg":
        # Short alias that applies the same category substitution generation
        # uses (engine_cascade.resolve_category_bg_path) — a literally-named
        # request like Regular/bg_wati.jpg must preview the actual reviewed
        # asset a real batch would get (bg_mangalsutra_short.jpg), not the
        # legacy file sitting at that literal name, otherwise the preview UI
        # and generation can silently disagree about which background an
        # operator is looking at.
        import engine_cascade
        relative = _safe_child(BACKGROUNDS, name)
        if not relative:
            return "Not found", 404
        theme = Path(name).parent.as_posix()
        stem = Path(name).stem
        category = stem[3:] if stem.startswith("bg_") else stem
        resolved = engine_cascade.resolve_category_bg_path(category, theme)
        if not resolved:
            return "Not found", 404
        return send_from_directory(resolved.parent, resolved.name)

    roots = {"input": INPUT, "processing": PROCESSING, "processed": PROCESSED, "output": OUTPUT, "backgrounds": BACKGROUNDS}
    root = roots.get(where)
    candidate = _safe_child(root, name) if root else None
    if not candidate or not candidate.is_file():
        return "Not found", 404
    return send_from_directory(root, candidate.relative_to(root).as_posix())


JOB = {
    "running": False, "paused": False, "total": 0, "done": 0, "current": "",
    "started": 0.0, "results": [], "error": None, "cancel_event": None, "token": 0,
}
CGPT_JOB = JOB  # Compatibility name used by retained tests and reset guards.
JOB_LOCK = threading.Lock()


def _atomic_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _publish_delivery(raw: Path, destination: Path) -> dict:
    import image_spec
    import enforce_symmetry
    import color_standardize
    from PIL import Image
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.{os.getpid()}.jpg")
    requested_edge = 3200
    selected_edge = None
    emergency_compression = False
    try:
        for edge in (3200, 3000, 2800, 2600, 2400, 2200, 2000):
            try:
                image_spec.convert_delivery_image(
                    str(raw),
                    str(temporary),
                    strategy="pad",
                    target_size=(edge, edge),
                    sharpen=True,
                    maximum_file_bytes=1_000_000,
                    minimum_jpeg_quality=88,
                )
                selected_edge = edge
                break
            except ValueError as exc:
                if "cannot fit within" not in str(exc):
                    raise
        if selected_edge is None:
            emergency_compression = True
            selected_edge = 2000
            image_spec.convert_delivery_image(
                str(raw),
                str(temporary),
                strategy="pad",
                target_size=(selected_edge, selected_edge),
                sharpen=True,
                maximum_file_bytes=1_000_000,
                minimum_jpeg_quality=1,
            )
        with Image.open(temporary) as delivered:
            symmetric = enforce_symmetry.enforce_pair_symmetry(delivered.convert("RGB"))
            standardized = color_standardize.standardize_gold(symmetric)
            standardized.save(temporary, format="JPEG", quality=92)
        os.replace(temporary, destination)
        raw.unlink(missing_ok=True)
        return {
            "requested_edge": requested_edge,
            "final_edge": selected_edge,
            "resolution_adjusted": selected_edge < requested_edge,
            "emergency_compression": emergency_compression,
            "file_bytes": destination.stat().st_size,
            "maximum_file_bytes": 1_000_000,
        }
    finally:
        temporary.unlink(missing_ok=True)


def _category_output_folder(category: str) -> str:
    stock_category = stock_category_map.BY_KEY.get(category)
    label = stock_category.label if stock_category else category.replace("_", " ")
    folder = re.sub(r"[^A-Za-z0-9]+", "", label.title())
    if not folder:
        raise ValueError(f"Invalid output category: {category}")
    return folder


def _run_batch(category: str, cancel: threading.Event, token: int, background: Path | None = None) -> None:
    import azure_catalogue_engine
    import processed_state

    items = _derive_single_items_from_disk()
    output_dir = OUTPUT / _category_output_folder(category)
    raw_dir = AZURE_REPORTS / "batches" / str(token)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    JOB["total"] = len(items)

    for index, item in enumerate(items, start=1):
        if cancel.is_set() or JOB.get("token") != token:
            break
        while JOB.get("paused") and not cancel.is_set():
            time.sleep(0.2)
        label = item["label"]
        safe = re.sub(r'[/\\:*?"<>|]', "_", label)
        source = INPUT / item["jewel"]
        raw = raw_dir / f"{index:04d}_{safe}.png"
        final = output_dir / f"{safe}.jpg"
        JOB["current"] = f"Azure FLUX.2 Pro · {index}/{len(items)} · {label}"
        try:
            if final.exists():
                raise RuntimeError(f"OUTPUT_EXISTS: {final}")
            if _duplicate_guard_enabled():
                import review_queue
                duplicate = review_queue.find_approved_duplicate(str(source), exclude_label=label)
                if duplicate:
                    raise RuntimeError(
                        f"DUPLICATE_OF_APPROVED: same photo already approved as {duplicate['label']}"
                    )
            generated = azure_catalogue_engine.generate(
                source, raw, background=background, category=category, cancel_event=cancel
            )
            delivery = _publish_delivery(Path(generated["output"]), final)
            hybrid = generated.get("hybrid_output")
            if hybrid:
                Path(hybrid).unlink(missing_ok=True)
            lifecycle = processed_state.record_success(
                str(source), label, category, processing_root=str(PROCESSING),
                legacy_input_root=str(INPUT), processed_root=str(PROCESSED)
            )
            if not lifecycle.get("moved"):
                raise RuntimeError(lifecycle.get("reason") or "source lifecycle transfer failed")
            processed_original = Path(lifecycle["path"]).resolve()
            original_relative = processed_original.relative_to(PROCESSED.resolve()).as_posix()
            result = {
                "pair": item["pair"], "ok": True, "sku": label, "engine": PROCESS_ENGINE,
                "output": final.relative_to(OUTPUT).as_posix(), "original": original_relative,
                "processed_lifecycle": lifecycle, "delivery": delivery,
                "delivery_flag": bool(delivery["resolution_adjusted"]),
            }
        except Exception as exc:
            result = {"pair": item["pair"], "ok": False, "sku": label, "engine": PROCESS_ENGINE, "error": str(exc)}
            if "BLOCKED:" in str(exc):
                JOB["error"] = str(exc)
                results.append(result)
                JOB.update(done=index, results=list(results))
                break
        results.append(result)
        JOB.update(done=index, results=list(results))
    JOB["current"] = JOB.get("error") or ("stopped" if cancel.is_set() else "done")


@app.post("/api/process/start")
def api_process_start():
    data = request.get_json(silent=True) or {}
    if not hmac.compare_digest(str(data.get("process_password") or ""), PROCESS_PASSWORD):
        return jsonify({"error": "Wrong processing password"}), 403
    if not prompt_governance.approval_status()["approved"]:
        return jsonify({"error": "Prompt review required before processing", "prompt_review_required": True}), 428
    category = str(data.get("category") or "").strip().lower()
    if category not in TYPES:
        return jsonify({"error": f"Unknown category: {category}"}), 400
    detected_category = session.get("detected_category")
    if detected_category and category != detected_category:
        expected = stock_category_map.BY_KEY.get(detected_category)
        return jsonify({
            "error": f"Category mismatch: source path/stock requires {expected.label if expected else detected_category}",
            "detected_category": detected_category,
        }), 409
    items = _derive_single_items_from_disk()
    if not items:
        return jsonify({"error": "no images found in input"}), 400
    background = None
    background_relative = str(data.get("background_path") or "").strip().replace("\\", "/")
    if background_relative:
        candidate = (BACKGROUNDS / Path(background_relative)).resolve()
        if not candidate.is_relative_to(BACKGROUNDS.resolve()) or not candidate.is_file() or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
            return jsonify({"error": "Invalid background selection"}), 400
        compatible = {item["path"] for item in background_library.compatible_backgrounds(BACKGROUNDS, category)}
        if background_relative not in compatible:
            return jsonify({"error": "Selected background is not compatible with this category"}), 409
        background = candidate
    with JOB_LOCK:
        if JOB["running"]:
            return jsonify({"error": "already running"}), 409
        token = int(JOB.get("token", 0)) + 1
        cancel = threading.Event()
        JOB.update(
            running=True, paused=False, total=len(items), done=0, current="Starting Azure FLUX.2 Pro",
            started=time.time(), results=[], error=None, cancel_event=cancel, token=token,
            batch_folder=session.get("batch_folder"),
            background=str(background) if background else None,
        )

    def guarded() -> None:
        try:
            _run_batch(category, cancel, token, background)
        except Exception as exc:
            JOB.update(error=f"AZURE_BATCH_CRASHED: {type(exc).__name__}: {exc}", current=str(exc))
        finally:
            if JOB.get("token") == token:
                JOB["running"] = False
            # Runs after every batch attempt, success or crash -- a stale
            # capture_intake/rejected overlap is exactly the kind of thing
            # that only shows up after enough runs to matter, so check every
            # time rather than relying on someone remembering to look.
            try:
                import review_queue
                dedup_report = review_queue.check_capture_rejected_dedup()
                # Always set, never just on failure -- otherwise a warning
                # from a past run would sit here forever once a later run
                # comes back clean, since nothing would ever clear it.
                JOB["dedup_warning"] = None if dedup_report["ok"] else dedup_report
            except Exception as exc:
                JOB["dedup_warning"] = {"ok": False, "error": f"dedup check itself failed: {exc}"}

    threading.Thread(target=guarded, daemon=True, name="azure-catalogue-batch").start()
    return jsonify({"started": True, "total": len(items), "engine": PROCESS_ENGINE})


@app.get("/api/process/progress")
def api_process_progress():
    elapsed = int(time.time() - JOB["started"]) if JOB["started"] else 0
    eta = int(elapsed / JOB["done"] * (JOB["total"] - JOB["done"])) if JOB["running"] and JOB["done"] else None
    return jsonify({
        "running": JOB["running"], "paused": JOB["paused"], "done": JOB["done"],
        "total": JOB["total"], "current": JOB["current"], "elapsed": elapsed, "eta": eta,
        "results": list(JOB["results"]), "error": JOB["error"], "engine": PROCESS_ENGINE,
    })


@app.post("/api/process/pause")
def api_process_pause():
    JOB["paused"] = bool((request.get_json(silent=True) or {}).get("paused", True))
    return jsonify({"ok": True, "paused": JOB["paused"]})


@app.post("/api/process/stop")
def api_process_stop():
    import azure_catalogue_engine
    event = JOB.get("cancel_event")
    if event:
        event.set()
    terminated = azure_catalogue_engine.cancel_active()
    JOB["paused"] = False
    JOB["current"] = "Stopping safely…" if JOB["running"] else "stopped"
    return jsonify({
        "ok": True,
        "was_running": bool(JOB["running"]),
        "active_call_terminated": terminated,
    })


@app.route("/api/engine/config", methods=["GET", "POST"])
def api_engine_config():
    if request.method == "POST":
        return jsonify({"error": "Engine switching is disabled", "engine_mode": PROCESS_ENGINE}), 403
    return jsonify({"engine_mode": PROCESS_ENGINE, "automatic_retries": 0})


def _duplicate_guard_enabled() -> bool:
    try:
        return bool(json.loads(DUPLICATE_GUARD_CONFIG.read_text(encoding="utf-8-sig")).get("enabled", True))
    except Exception:
        return True


@app.get("/api/duplicate-guard")
def api_duplicate_guard_get():
    return jsonify({"enabled": _duplicate_guard_enabled()})


@app.post("/api/duplicate-guard")
def api_duplicate_guard_set():
    enabled = bool((request.get_json(silent=True) or {}).get("enabled", True))
    _atomic_json(DUPLICATE_GUARD_CONFIG, {"enabled": enabled})
    return jsonify({"enabled": enabled})


@app.get("/api/prompt")
def api_prompt():
    return jsonify(prompt_governance.approval_status())


@app.post("/api/prompt/approve")
def api_prompt_approve():
    data = request.get_json(silent=True) or {}
    current = prompt_governance.current()
    if not hmac.compare_digest(str(data.get("prompt_sha256") or ""), current["prompt_sha256"]):
        return jsonify({"error": "Prompt changed; reload and review again"}), 409
    return jsonify(prompt_governance.approve(str(data.get("reviewed_by") or "catalogue owner")))


def _azure_usage() -> dict:
    config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    usage_file = AZURE_REPORTS / "usage.json"
    usage = json.loads(usage_file.read_text(encoding="utf-8-sig")) if usage_file.is_file() else {"records": []}
    records = usage.get("records") or []
    today = datetime.now(timezone.utc).date().isoformat()
    today_records = [row for row in records if str(row.get("reserved_at_utc", "")).startswith(today)]
    historical = float(config.get("historical_estimated_spend_usd", 0))
    reserved = sum(float(row.get("reserved_usd", 0)) for row in records)
    return {
        "model": "FLUX.2 Pro", "lifetime_reserved_usd": round(historical + reserved, 2),
        "lifetime_cap_usd": float(config["lifetime_hard_cap_usd"]),
        "today_reserved_usd": round(sum(float(row.get("reserved_usd", 0)) for row in today_records), 2),
        "daily_cap_usd": float(config["daily_hard_cap_usd"]), "today_calls": len(today_records),
        "daily_call_cap": int(config["maximum_calls_per_day"]), "automatic_retries": 0,
    }


@app.get("/api/azure/usage")
def api_azure_usage():
    try:
        return jsonify(_azure_usage())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@app.get("/azure-cost")
def azure_cost_dashboard():
    dashboard = AZURE_REPORTS / "COST_DASHBOARD.html"
    if not dashboard.is_file():
        subprocess.run([sys.executable, str(BASE / "tools" / "azure_flux2_guarded.py"), "--dashboard-only"], cwd=BASE, timeout=30, check=False)
    return send_from_directory(AZURE_REPORTS, dashboard.name)


@app.get("/api/health")
def api_health():
    checks = {}
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        key = Path(config["encrypted_key_file"])
        if not key.is_file():
            raise FileNotFoundError("protected key missing")
        clear_key = win32crypt.CryptUnprotectData(key.read_bytes(), None, None, None, 0)[1]
        key_ok = len(clear_key) >= 12
        clear_key = b""
        checks["azure"] = {
            "ok": key_ok,
            "detail": "guard config present; service can decrypt protected key" if key_ok else "protected key is invalid",
        }
    except Exception as exc:
        checks["azure"] = {"ok": False, "detail": str(exc)}
    try:
        probe = OUTPUT / ".health_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks["disk"] = {"ok": True, "detail": "output writable"}
    except Exception as exc:
        checks["disk"] = {"ok": False, "detail": str(exc)}
    try:
        with socket.create_connection(("127.0.0.1", 7660), timeout=0.3):
            checks["capture"] = {"ok": True, "detail": "capture service reachable"}
    except OSError:
        checks["capture"] = {"ok": False, "detail": "capture service offline"}
    return jsonify({"ok": all(item["ok"] for item in checks.values()), "checks": checks, "ts": time.time()})


@app.get("/api/stock/reconciliation")
def api_stock_reconciliation():
    import stock_reconciliation
    try:
        return jsonify(stock_reconciliation.status(reconcile=False))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409


@app.get("/api/review/batches")
def api_review_batches():
    import review_queue
    category = request.args.get("category", "").strip() or None
    return jsonify({"batches": review_queue.list_batches(category)})


@app.get("/api/review/items")
def api_review_items():
    import review_queue
    category = request.args.get("category", "").strip() or None
    items = review_queue.collect_items(category)
    batch = request.args.get("batch")
    if batch:
        batches = {str(row["batch"]): row for row in review_queue.list_batches(category)}
        keep = set(batches.get(str(batch), {}).get("labels", []))
        items = [item for item in items if item["label"] in keep]
    for item in items:
        item["has_original"] = bool(item.pop("original", None))
        item.pop("edited", None)
        item.pop("_edited_path", None)
    return jsonify({"items": items, "summary": review_queue.folder_summary(category)})


@app.get("/api/review/reasons")
def api_review_reasons():
    import review_queue
    return jsonify({"reasons": review_queue.reason_catalogue()})


@app.post("/api/review/verdict")
def api_review_verdict():
    import review_queue
    data = request.get_json(silent=True) or {}
    label = str(data.get("label") or "").strip()
    if not label:
        return jsonify({"error": "no label"}), 400
    try:
        saved = review_queue.set_verdict(label, str(data.get("verdict") or ""), data.get("reason"), note=data.get("note"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    category = str(data.get("category") or "").strip() or None
    return jsonify({"ok": True, "saved": saved, "summary": review_queue.folder_summary(category)})


@app.post("/api/review/requeue")
def api_review_requeue():
    import review_queue
    labels = [str(value).strip() for value in (request.get_json(silent=True) or {}).get("labels", []) if str(value).strip()]
    return jsonify(review_queue.requeue(labels)) if labels else (jsonify({"error": "no labels"}), 400)


@app.get("/review_img/<side>/<label>")
def review_image(side: str, label: str):
    import review_queue
    safe_label = Path(label).name
    path = review_queue._find_original(safe_label) if side == "original" else next((item.get("edited") for item in review_queue.collect_items() if item["label"] == safe_label), None)
    return send_from_directory(Path(path).parent, Path(path).name) if path and Path(path).is_file() else ("not found", 404)


def _count(root: Path) -> int:
    return len(_images(root, recursive=True))


def _get_lifecycle_requeue_service():
    import lifecycle_requeue
    return lifecycle_requeue.LifecycleRequeueService(processing_root=PROCESSING, needs_review_root=NEEDS_REVIEW, rejected_root=REJECTED)


def _get_routing_preview_service():
    return routing_preview.RoutingPreviewService()


# ── Manual model-pose override ──────────────────────────────────────────────
# A manually pinned model reference (model_cfg["modelPath"]) is normally
# required to match the category's expected anatomical zone (earrings need a
# face-zone pose, not a feet-zone one) — a silent mismatch there produces a
# genuinely wrong composite (jewellery pasted onto the wrong body part) with
# no visible error. allowPoseOverride is the explicit, opt-in escape hatch
# for when an operator really does want a non-standard pose.

def _resolve_model_ref(category: str, model_cfg: dict):
    import item_routing
    import ornament_placement

    model_path = (model_cfg or {}).get("modelPath")
    if not model_path:
        return None, None

    try:
        resolved = item_routing._resolve_inside(Path(MODELS_DIR), Path(model_path))
    except item_routing.RoutingError as exc:
        raise ValueError(f"MODEL_REFERENCE_INVALID: {exc}")

    if not resolved.is_file():
        raise ValueError(f"MODEL_REFERENCE_NOT_FOUND: {model_path}")

    if not (model_cfg or {}).get("allowPoseOverride"):
        _, expected_zone, _ = ornament_placement.template_profile(category)
        actual_zone = item_routing._model_zone(resolved.name)
        if expected_zone and actual_zone and actual_zone != expected_zone:
            raise ValueError(
                f"MODEL_POSE_MISMATCH: {resolved.name} looks like a {actual_zone!r} pose, "
                f"expected {expected_zone!r} for {category}. Set allowPoseOverride to use it anyway."
            )

    return str(resolved), None


def _cycled_model_cfg(model_cfg: dict, index: int) -> dict:
    """One config per pair from a multi-model batch — a shallow copy so the
    batch's shared config (and every other pair reading it concurrently)
    is never mutated by one pair's cycle position."""
    cfg = dict(model_cfg or {})
    model_paths = cfg.get("modelPaths") or []
    if model_paths:
        cfg["modelPath"] = model_paths[index % len(model_paths)]
    return cfg


@app.route("/api/model_images")
def api_model_images():
    import item_routing
    import ornament_placement

    category = request.args.get("category", "")
    group = request.args.get("group", "")
    style = request.args.get("style", "")
    include_all_poses = request.args.get("include_all_poses") == "1"

    _, expected_zone, _ = ornament_placement.template_profile(category)
    root = Path(MODELS_DIR) / group / style
    images = []
    if root.is_dir():
        for candidate in sorted(root.iterdir()):
            if candidate.is_file() and candidate.suffix.casefold() in IMAGE_EXTENSIONS:
                zone = item_routing._model_zone(candidate.name)
                if include_all_poses or not expected_zone or zone is None or zone == expected_zone:
                    images.append({
                        "path": candidate.relative_to(Path(MODELS_DIR)).as_posix(),
                    })
    return jsonify({"images": images, "expected_zone": expected_zone})


# ── Pipeline dashboard ──────────────────────────────────────────────────────

class PipelineCoordinator:
    """Owns the last-known-good stock snapshot so a failed refresh (bad
    workbook, share offline) degrades to stale-but-present numbers instead of
    zeroing the whole dashboard — the health segment still reports the
    failure honestly, it just doesn't nuke stock_tags/stock_pieces."""

    def __init__(self):
        self._last_snapshot = None

    def refresh_stock(self):
        workbook = stock_excel.latest_stock_workbook()
        snapshot = stock_excel.load_stock_workbook(workbook)
        self._last_snapshot = snapshot
        return SimpleNamespace(inventory=snapshot, warning=None)

    def dashboard(self, *, now, timezone, external_health):
        return dashboard_stats.collect_dashboard_stats(
            capture_root=paths.CAPTURE_DIR,
            processing_root=paths.PROCESSING_DIR,
            processed_root=paths.PROCESSED_DIR,
            needs_review_root=paths.NEEDS_REVIEW_DIR,
            rejected_root=paths.REJECTED_DIR,
            stock_snapshot=self._last_snapshot,
            now=now,
            timezone=timezone,
            external_health=external_health,
        )


_PIPELINE_COORDINATOR = None


def _get_pipeline_coordinator():
    global _PIPELINE_COORDINATOR
    if _PIPELINE_COORDINATOR is None:
        _PIPELINE_COORDINATOR = PipelineCoordinator()
    return _PIPELINE_COORDINATOR


def _cached_pipeline_system_health():
    # Reuses /api/health's own checks (azure key decrypt, disk writable,
    # capture service reachable) rather than re-deriving a second, possibly
    # drifting notion of "healthy" for the dashboard specifically.
    return api_health().get_json()["checks"]


@app.route("/api/pipeline/dashboard")
def api_pipeline_dashboard():
    coordinator = _get_pipeline_coordinator()
    stock_error = None
    refresh_result = None
    try:
        refresh_result = coordinator.refresh_stock()
    except Exception as exc:
        stock_error = str(exc)

    now = datetime.now(tz=timezone.utc)
    stats = coordinator.dashboard(now=now, timezone=timezone.utc,
                                   external_health=_cached_pipeline_system_health())
    payload = stats.as_dict()
    payload["stock_source"] = None
    payload["stock_updated_at"] = None

    if stock_error:
        payload.setdefault("health", {})["stock"] = {"ok": False, "detail": stock_error}
    elif refresh_result is not None:
        inventory = getattr(refresh_result, "inventory", None)
        source_path = getattr(inventory, "source_path", None) if inventory is not None else None
        if source_path is not None:
            payload["stock_source"] = Path(source_path).name
            payload["stock_updated_at"] = now.isoformat()
        warning = getattr(refresh_result, "warning", None)
        if warning:
            payload.setdefault("health", {})["stock"] = {"ok": True, "detail": warning}

    payload["latest_capture"] = _latest_capture_record()
    return jsonify(payload)


@app.route("/api/pipeline/category_breakdown")
def api_pipeline_category_breakdown():
    import orn_item_image_sync
    import review_queue

    coordinator = _get_pipeline_coordinator()
    stock_labels = coordinator._last_snapshot.records if coordinator._last_snapshot else ()
    stock_labels = [record.label_no for record in stock_labels]
    rows = category_dashboard.category_breakdown(
        capture_root=str(paths.CAPTURE_DIR),
        processed_root=str(paths.PROCESSED_DIR),
        stock_labels=stock_labels,
        review_state=review_queue._load_state(),
        uploaded_labels=orn_item_image_sync.uploaded_labels(),
    )
    upload_status = orn_item_image_sync._load_json(orn_item_image_sync.STATUS)
    upload_queue = orn_item_image_sync._load_json(orn_item_image_sync.QUEUE)
    return jsonify({
        "categories": rows,
        "updated_at": time.time(),
        "upload_root_reachable": not upload_queue and not upload_status.get("failed"),
        "upload_queue": len(upload_queue),
    })


def _latest_capture_record():
    dedup = capture_tool._load_dedup()
    if not dedup:
        return None
    tag, info = max(dedup.items(), key=lambda kv: kv[1].get("ts", 0))
    relative_path = f"{info.get('folder', '')}/{info.get('filename', '')}"
    return {
        "tag": tag,
        "relative_path": relative_path,
        "preview_url": f"/api/pipeline/latest_capture_preview?v={info.get('ts', 0)}",
    }


@app.route("/api/pipeline/latest_capture_preview")
def api_pipeline_latest_capture_preview():
    latest = _latest_capture_record()
    if not latest:
        return jsonify({"error": "no captures yet"}), 404
    full_path = os.path.join(capture_tool.CAPTURE_ROOT, *latest["relative_path"].split("/"))
    if not os.path.isfile(full_path):
        return jsonify({"error": "capture file missing"}), 404
    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))


@app.route("/api/capture/live_status")
def api_capture_live_status():
    try:
        with socket.create_connection(("127.0.0.1", 7660), timeout=0.3):
            reachable = True
    except OSError:
        reachable = False
    try:
        sessions = capture_tool.all_sessions_summary()
    except Exception:
        sessions = []
    active_trays = {
        session.get("category", session.get("folder", str(i))): session.get("folder", "")
        for i, session in enumerate(sessions)
        if session.get("open") or session.get("active")
    }
    return jsonify({"reachable": reachable, "active_trays": active_trays})


_PIPELINE_LIVE_CACHE = {"expires_at": 0.0, "payload": None, "signature": None, "generation": 0}
_PIPELINE_LIVE_LOCK = threading.Lock()


def _pipeline_live_signature():
    """Cheap, fast-to-compute signature so an unchanged filesystem state can
    skip redoing the real (directory-walking) work on every 1s poll."""
    try:
        capture_mtime = os.path.getmtime(paths.CAPTURE_DIR) if os.path.isdir(paths.CAPTURE_DIR) else 0
        processed_mtime = os.path.getmtime(paths.PROCESSED_DIR) if os.path.isdir(paths.PROCESSED_DIR) else 0
    except OSError:
        capture_mtime = processed_mtime = 0
    return (capture_mtime, processed_mtime)


@app.route("/api/pipeline/live_snapshot")
def api_pipeline_live_snapshot():
    now = time.time()
    with _PIPELINE_LIVE_LOCK:
        cache = _PIPELINE_LIVE_CACHE
        signature = _pipeline_live_signature()
        if (cache["payload"] is not None and cache["signature"] == signature
                and now < cache["expires_at"]):
            return jsonify(cache["payload"])

        dashboard = api_pipeline_dashboard().get_json()
        categories = api_pipeline_category_breakdown().get_json()
        capture = api_capture_live_status().get_json()
        generation = cache["generation"] + 1
        payload = {
            "dashboard": dashboard,
            "categories": categories.get("categories", []),
            "capture": capture,
            "generation": generation,
        }
        cache.update({
            "expires_at": now + 1.0,
            "payload": payload,
            "signature": signature,
            "generation": generation,
        })
        return jsonify(payload)


@app.route("/api/pipeline/routing/preview", methods=["POST"])
def api_routing_preview():
    data = request.get_json(force=True) or {}
    service = _get_routing_preview_service()
    try:
        result = service.preview(
            tag_label=data.get("tag_label", ""),
            ornament_type=data.get("ornament_type", ""),
            manual_override=data.get("manual_override"),
        )
    except routing_preview.RoutingPreviewValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except routing_preview.RoutingPreviewTagNotFound as exc:
        return jsonify({"error": str(exc)}), 404
    except routing_preview.RoutingPreviewConflict as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(result), 200


@app.route("/api/pipeline/requeue/preview", methods=["GET"])
def api_pipeline_requeue_preview():
    import lifecycle_requeue
    service = _get_lifecycle_requeue_service()
    try:
        return jsonify(service.preview(request.args.get("status", ""), request.args.get("path", "")))
    except lifecycle_requeue.RequeueSourceNotFound as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except lifecycle_requeue.RequeueValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/pipeline/requeue", methods=["GET", "POST"])
def api_pipeline_requeue():
    import lifecycle_requeue
    service = _get_lifecycle_requeue_service()
    try:
        if request.method == "GET":
            status = request.args.get("status", "")
            return jsonify({"ok": True, "status": status, "items": [item.as_dict() for item in service.list_items(status)]})
        data = request.get_json(silent=True) or {}
        return jsonify(service.requeue(data.get("status"), data.get("path"), data.get("confirmation_token")))
    except lifecycle_requeue.RequeueConflictError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    except lifecycle_requeue.RequeueSourceNotFound as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except lifecycle_requeue.RequeueValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/pipeline/processed_reset/preview")
def api_processed_reset_preview():
    import processed_state
    try:
        tags = processed_state.parse_tag_series(request.args.get("tags", ""))
        if not tags:
            raise ValueError("Enter at least one tag")
        preview = processed_state.preview_reset(tags)
        return jsonify({"ok": True, "scope": "tags", **preview.as_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def _processed_reset_blocked() -> bool:
    return bool(JOB["running"])


@app.post("/api/pipeline/processed_reset")
def api_processed_reset():
    import processed_state
    data = request.get_json(silent=True) or {}
    scope = str(data.get("scope") or "tags")
    required_confirmation = "RESET ALL PROCESSED" if scope == "all" else "RESET SELECTED PROCESSED"
    if str(data.get("confirmation") or "") != required_confirmation:
        return jsonify({"ok": False, "error": f"Type exactly {required_confirmation!r} to confirm."}), 400
    if _processed_reset_blocked():
        return jsonify({"ok": False, "error": "Stop Manual/Auto processing before resetting"}), 409
    try:
        if scope == "all":
            result = processed_state.apply_reset(None)
        else:
            tags = processed_state.parse_tag_series(str(data.get("tags") or ""))
            if not tags:
                raise ValueError("Enter at least one tag")
            result = processed_state.apply_reset(tags)
        return jsonify({"ok": True, "scope": scope, **result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409


def _acquire_single_instance_lock() -> None:
    """Kernel-level singleton guard: exactly one server process may run on
    this machine at a time.

    Port binding alone doesn't reliably enforce this on Windows -- without
    SO_EXCLUSIVEADDRUSE, multiple processes can each successfully LISTEN on
    the same port, and the OS hands each new connection to an
    implementation-defined one of them. That's exactly how this got found:
    three stale `python app.py` processes ended up simultaneously bound to
    :7654, and a login could land on whichever one still had the old
    password in memory. A named Win32 mutex has no such ambiguity --
    CreateMutex is atomic at the kernel level, so a second process asking
    for the same name always gets told, unambiguously, that it already
    exists. The OS releases it automatically the instant this process
    exits, so a crashed/killed instance never leaves a stale lock behind.
    """
    import win32event
    import win32api
    import winerror

    global _SINGLE_INSTANCE_MUTEX
    _SINGLE_INSTANCE_MUTEX = win32event.CreateMutex(
        None, False, "Global\\AmbicCatalogueStudio_SingleInstance"
    )
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        print(
            "Another Ambic Catalogue Studio server is already running on this "
            "PC. Refusing to start a second instance -- close the existing one "
            "first if you actually need to restart it."
        )
        raise SystemExit(0)


if __name__ == "__main__":
    _acquire_single_instance_lock()

    import review_queue

    route_report = review_queue.reconcile_source_routes()
    print(
        "Raw-master routing: "
        f"checked={route_report['checked']} repaired={route_report['repaired']} "
        f"conflicts={len(route_report['conflicts'])} missing={len(route_report['missing'])}"
    )
    stock_watcher.start_daemon()
    port = int(os.environ.get("CATALOGUE_PORT", "7654"))
    (BASE / "port.txt").write_text(str(port), encoding="ascii")
    print(f"Catalogue V2: http://0.0.0.0:{port} (LAN reachable)")
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
