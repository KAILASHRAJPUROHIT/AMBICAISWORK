"""
capture_server.py — standalone capture-tool server, fully isolated from
app.py (the main catalogue/generation tool).

WHY THIS EXISTS: every real production outage this session traced back to
capture sharing a process with the main tool's Copilot/Gemini/Codex engine
machinery — a slow/hung health check, a stray background script contending
for the same Chrome tabs, an orphaned process, all of it could (and did)
degrade or crash the shared Flask process capture also depended on. This
module has ZERO imports from app.py, copilot_img, gemini_img,
gemini_web_chat, codex_img, chatgpt_conv_img, engine_stats, or
engine_advisor — it only touches capture_tool.py (pure file I/O, no browser
automation, no external engine calls at all) and Flask itself. Nothing that
happens in the main tool's process — a crash, a hang, a restart, a
generation script hammering Copilot — can reach this process at all, since
it isn't the same process and shares no code path with it at runtime.

Runs on its own port (default 7660), with its own login session, so it
keeps working even if the main tool's process (port 7654) is completely
down. Supervised independently — see supervisor.ps1's capture-specific
check block and launch_capture.vbs.

Data files (capture_intake/, capture_dedup.json, capture_current_tray.json)
are the exact same files capture_tool.py has always used — nothing about
where captured data lives changes. Only ONE process should ever serve
capture routes at a time; app.py's own /api/capture/* routes have been
removed in favor of a redirect to this server, specifically so the
in-process locks inside capture_tool.py (which only coordinate threads
within a single process) are never bypassed by two processes writing the
same tray/dedup files concurrently.
"""
import ipaddress
import json
import logging
import os
import socket
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_from_directory
from werkzeug.serving import WSGIRequestHandler
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

BASE = os.path.dirname(os.path.abspath(__file__))
# Duplicated deliberately, not imported from app.py -- see module docstring
# on process isolation. Same computed value app.py's OUTPUT resolves to.
OUTPUT = os.path.join(BASE, "output")
PORT = int(os.environ.get("CAPTURE_PORT", "7660"))
_SSL_CERT_PATH = os.path.join(BASE, "data", "capture_https_cert.pem")
_SSL_KEY_PATH = os.path.join(BASE, "data", "capture_https_key.pem")
_SSL_META_PATH = os.path.join(BASE, "data", "capture_https_meta.json")

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

_SECRET_KEY_PATH = os.path.join(BASE, "data", "capture_secret_key.txt")


def _load_or_create_secret_key():
    if os.path.exists(_SECRET_KEY_PATH):
        with open(_SECRET_KEY_PATH, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    import secrets
    key = secrets.token_hex(32)
    with open(_SECRET_KEY_PATH, "w", encoding="utf-8") as f:
        f.write(key)
    return key


app.secret_key = _load_or_create_secret_key()
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30



# TYPES kept minimal and local — capture only needs category labels, not the
# main tool's full generation-template setup. Mirrors app.py's TYPES list;
# update both if a new ornament category is ever added. Sourced from
# stock_category_map.py — see capture_tool.CATEGORY_LABELS for the full
# rationale (real, verified stock categories; "silver"/"diamond" added
# separately, a different concern the new sheet doesn't cover).
import stock_category_map as _scm

TYPES = [c.key for c in _scm.CATEGORIES] + ["silver", "diamond"]


def _capture_page_version():
    try:
        return os.path.getmtime(os.path.join(BASE, "templates", "capture.html"))
    except OSError:
        return 0


@app.route("/")
@app.route("/capture")
def capture_page():
    import capture_tool as ct
    response = render_template("capture.html", categories=ct.category_list(TYPES + [ct.TEST_CATEGORY]),
                               capture_version=_capture_page_version())
    # The page itself carries no versioned query string (unlike the worker
    # script below), so without an explicit no-store a phone browser can
    # keep serving a stale cached copy of the capture flow after an update
    # even though the server is already running the new code.
    resp = app.make_response(response)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/api/stock/reconciliation")
def api_stock_reconciliation():
    """Apply a validated daily stock delta and return uncaptured additions."""
    import stock_reconciliation
    try:
        return jsonify(stock_reconciliation.status(reconcile=False))
    except stock_reconciliation.StockReconciliationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/capture/session_summary")
def api_capture_session_summary():
    import capture_tool as ct
    category = (request.args.get("category") or "").strip()
    # Reject a missing/unknown category instead of proceeding. session_summary
    # auto-creates tray #1 for whatever it is handed, so an empty category
    # produced a real folder literally named " 1" on disk plus an "" key in
    # capture_current_tray.json — junk state created by nothing more than a
    # request with a missing query param, and start_new_tray already guards
    # this exact case.
    if not category or category not in ct.CATEGORY_LABELS:
        return jsonify({"ok": False,
                        "error": f"missing or unknown category: {category!r}"}), 400
    summary = ct.session_summary(category)
    summary["items"] = ct.tray_items(summary["folder"]) if summary.get("folder") else []
    return jsonify(summary)


@app.route("/api/capture/start_new_tray", methods=["POST"])
def api_capture_start_new_tray():
    import capture_tool as ct
    category = request.form.get("category") or (request.get_json(silent=True) or {}).get("category", "")
    # A stale browser tab (open from before a category taxonomy change,
    # e.g. the pre-2026-08 legacy keys like "earrings"/"gents_rings") could
    # still submit a category that no longer exists in the current
    # CATEGORY_LABELS. Unlike session_summary, this route never checked —
    # it happily reserved (and, before tray creation was made lazy,
    # immediately created on disk) a tray for a dead category no one could
    # ever see or capture into again.
    if not category or category not in ct.CATEGORY_LABELS:
        return jsonify({"ok": False, "error": f"missing or unknown category: {category!r}"}), 400
    tray = ct.start_new_tray(category)
    return jsonify({"ok": True, **tray})


@app.route("/api/capture/all_sessions")
def api_capture_all_sessions():
    import capture_tool as ct
    return jsonify({"sessions": ct.all_sessions_summary()})


@app.route("/api/capture/check_duplicate")
def api_capture_check_duplicate():
    import capture_tool as ct
    tag_code = request.args.get("tag_code", "")
    prior = ct.check_duplicate(tag_code)
    return jsonify({"duplicate": prior is not None, "prior": prior})


@app.route("/api/capture/search_item")
def api_capture_search_item():
    """Look up one captured item by its exact tag code — replaces the old
    whole-folder Forget with a search-then-delete flow scoped to a single
    item."""
    import capture_tool as ct
    tag_code = request.args.get("tag_code", "").strip()
    if not tag_code:
        return jsonify({"ok": False, "error": "missing tag_code"}), 400
    item = ct.find_item(tag_code)
    if item is None:
        return jsonify({"ok": False, "error": f"no captured item found for tag {tag_code!r}"}), 404
    return jsonify({"ok": True, "item": item})


@app.route("/api/capture/delete_item", methods=["POST"])
def api_capture_delete_item():
    """Permanently delete one item's jewel + tag photo and its dedup record.
    Requires the caller to echo the exact tag code back as confirmation,
    same pattern as the old clear_folder's confirm_folder — a rare,
    deliberate, irreversible action must never fire from a single tap."""
    import capture_tool as ct
    tag_code = request.form.get("tag_code", "").strip()
    confirm = request.form.get("confirm_tag_code", "").strip()
    if not tag_code:
        return jsonify({"ok": False, "error": "missing tag_code"}), 400
    if confirm != tag_code:
        return jsonify({"ok": False, "error": "confirmation did not match"}), 400
    result = ct.delete_item(tag_code)
    return jsonify(result), (200 if result.get("ok") else 404)


@app.route("/api/capture/resolve_category")
def api_capture_resolve_category():
    """The tag's own code prefix is the sole source of truth for its
    category — the operator never chooses one. Called client-side right
    after a tag's barcode/QR is decoded, before the confirm/save step, so
    the screen can show and act on the right category with no manual
    picker anywhere in the flow."""
    import ornament_code_map as ocm
    tag_code = request.args.get("tag_code", "")
    cat = ocm.category_from_tag_code(tag_code)
    if not cat:
        return jsonify({"ok": False, "error": f"unrecognised tag code prefix: {tag_code!r}"}), 404
    return jsonify({"ok": True, "key": cat.key, "label": cat.label, "prefix": cat.prefix})


# ── Multi-angle calibration (RSC 2 category profiles) ────────────────────────
# Calibration belongs to the CATEGORY, resolved above via resolve_category —
# never to an individual tag. See calibration_repository.py's own docstring.

def _profile_to_json(profile):
    return {
        "categoryKey": profile.category_key,
        "displayName": profile.display_name,
        "status": profile.status,
        "main": profile.main.as_dict(),
        "angle1": profile.angle1.as_dict(),
        "angle2": profile.angle2.as_dict(),
        "derivedFromCategoryKey": profile.derived_from_category_key,
        "version": profile.version,
        "createdAt": profile.created_at,
        "updatedAt": profile.updated_at,
    }


def _pose_from_json(d):
    import calibration_repository as cal
    if not isinstance(d, dict):
        raise ValueError("pose must be an object with yaw/pitch/roll")
    return cal.CapturePose.from_dict(d)


@app.route("/api/capture/calibration/status")
def api_calibration_status():
    import calibration_repository as cal
    return jsonify(cal.repository.get_calibration_status())


@app.route("/api/capture/calibration/<category_key>")
def api_calibration_get(category_key):
    import calibration_repository as cal
    profile = cal.repository.get_profile(category_key)
    if profile is None:
        return jsonify({"ok": False, "error": "not_configured"}), 404
    return jsonify({"ok": True, "profile": _profile_to_json(profile)})


@app.route("/api/capture/calibration", methods=["POST"])
def api_calibration_save():
    """Save a fresh (or fine-tuned) profile for a category. The category
    display name is taken from ornament_code_map — the source of truth for
    the visible label (spec rule 10) — not from client-supplied text."""
    import calibration_repository as cal
    import ornament_code_map as ocm
    body = request.get_json(silent=True) or {}
    category_key = body.get("categoryKey", "")
    cat = ocm.BY_KEY.get(category_key)
    if not cat:
        return jsonify({"ok": False, "error": f"unknown category key: {category_key!r}"}), 400
    try:
        main = _pose_from_json(body.get("main"))
        angle1 = _pose_from_json(body.get("angle1"))
        angle2 = _pose_from_json(body.get("angle2"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    warnings = cal.check_pose_separation(main, angle1, angle2)
    if warnings and not body.get("acceptCloseAngles"):
        return jsonify({"ok": False, "error": "angles_too_close", "warnings": warnings}), 409

    existing = cal.repository.get_profile(category_key)
    derived_from = existing.derived_from_category_key if existing else None
    status = cal.STATUS_COPIED_AND_MODIFIED if derived_from else cal.STATUS_CALIBRATED
    profile = cal.CategoryCaptureProfile(
        category_key=category_key,
        display_name=cat.label,
        status=status,
        main=main, angle1=angle1, angle2=angle2,
        derived_from_category_key=derived_from,
        version=(existing.version + 1) if existing else 1,
        created_at=existing.created_at if existing else time.time(),
    )
    cal.repository.save_profile(profile)
    return jsonify({"ok": True, "profile": _profile_to_json(profile)})


@app.route("/api/capture/calibration/copy", methods=["POST"])
def api_calibration_copy():
    import calibration_repository as cal
    body = request.get_json(silent=True) or {}
    source = body.get("sourceCategoryKey", "")
    destination = body.get("destinationCategoryKey", "")
    if not source or not destination:
        return jsonify({"ok": False, "error": "sourceCategoryKey and destinationCategoryKey required"}), 400
    try:
        profile = cal.repository.copy_profile(source, destination)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "profile": _profile_to_json(profile)})


@app.route("/api/capture/calibration/<category_key>", methods=["DELETE"])
def api_calibration_delete(category_key):
    import calibration_repository as cal
    cal.repository.delete_profile(category_key)
    return jsonify({"ok": True})


@app.route("/api/capture/calibration/export")
def api_calibration_export():
    import calibration_repository as cal
    return jsonify(cal.repository.export_backup())


@app.route("/api/capture/calibration/import", methods=["POST"])
def api_calibration_import():
    import calibration_repository as cal
    body = request.get_json(silent=True) or {}
    overwrite = bool(body.get("overwrite"))
    try:
        count = cal.repository.import_backup(body, overwrite=overwrite)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "imported": count})


# ── Capture history admin ────────────────────────────────────────────────────
# "Forget" is intentionally destructive: after a separately fetched preview
# and an exact confirmation token, it removes the selected tray's downstream
# pipeline/output copies and dedup history. Raw capture/master folders are
# immutable and are never deleted by this route.


@app.route("/api/capture/memory")
def api_capture_memory():
    import capture_tool as ct
    import capture_purge
    return jsonify({
        "enabled": ct.dedup_enabled(),
        "folders": capture_purge.list_capture_histories(ct),
    })


@app.route("/api/capture/memory/toggle", methods=["POST"])
def api_capture_memory_toggle():
    import capture_tool as ct
    body = request.form if request.form else (request.get_json(silent=True) or {})
    raw = body.get("enabled")
    # Explicit parse, no truthiness: the string "false" arriving from a form
    # post is truthy in Python, which would turn the switch ON when the user
    # asked for OFF — silently disabling nothing while reporting success.
    if isinstance(raw, bool):
        enabled = raw
    elif isinstance(raw, str) and raw.strip().lower() in ("1", "true", "on", "yes"):
        enabled = True
    elif isinstance(raw, str) and raw.strip().lower() in ("0", "false", "off", "no"):
        enabled = False
    else:
        return jsonify({"ok": False, "error": f"invalid 'enabled' value: {raw!r}"}), 400
    return jsonify({"ok": True, "enabled": ct.set_dedup_enabled(enabled)})


@app.route("/api/capture/memory/purge_preview", methods=["POST"])
def api_capture_memory_purge_preview():
    import capture_tool as ct
    import capture_purge
    body = request.form if request.form else (request.get_json(silent=True) or {})
    folder = (body.get("folder") or "").strip()
    if not folder:
        return jsonify({"ok": False, "error": "missing folder"}), 400
    try:
        preview = capture_purge.preview_folder_history(ct, folder)
    except capture_purge.CapturePurgeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **preview.as_dict()})


@app.route("/api/capture/memory/clear_folder", methods=["POST"])
def api_capture_memory_clear_folder():
    import capture_tool as ct
    import capture_purge
    import stock_reconciliation
    body = request.form if request.form else (request.get_json(silent=True) or {})
    folder = (body.get("folder") or "").strip()
    if not folder:
        return jsonify({"ok": False, "error": "missing folder"}), 400
    try:
        capture_purge.preview_folder_history(ct, folder)
    except capture_purge.CapturePurgeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    if body.get("confirm_folder") != folder:
        return jsonify({
            "ok": False,
            "error": "permanent deletion requires exact folder confirmation",
        }), 400
    with stock_reconciliation.data_lock():
        result = capture_purge.purge_folder_history(ct, folder)
    return jsonify(result), (200 if result["ok"] else 500)


@app.route("/api/capture/undo_last", methods=["POST"])
def api_capture_undo_last():
    import capture_tool as ct
    category = request.form.get("category") or (request.get_json(silent=True) or {}).get("category", "")
    if not category or category not in ct.CATEGORY_LABELS:
        return jsonify({"ok": False, "error": f"missing or unknown category: {category!r}"}), 400
    return jsonify(ct.undo_last(category))


@app.route("/api/capture/save", methods=["POST"])
def api_capture_save():
    import capture_tool as ct
    import ornament_code_map as ocm
    category = request.form.get("category", "")
    tag_code = request.form.get("tag_code", "")
    staff_name = request.form.get("staff_name", "")
    override_duplicate = request.form.get("override_duplicate") == "1"
    override_blur = request.form.get("override_blur") == "1"
    override_visibility = request.form.get("override_visibility") == "1"
    jewel_file = request.files.get("jewel")
    tag_file = request.files.get("tag")
    if not category and tag_code:
        # The tag's code is already known the moment its barcode/QR is
        # decoded (client-side, before this request is even sent) — the
        # code prefix alone determines its category, so the operator no
        # longer has to pick one by hand.
        auto = ocm.category_from_tag_code(tag_code)
        if auto:
            category = auto.key
    if not category or category not in ct.CATEGORY_LABELS:
        return jsonify({"ok": False, "error": f"missing or unknown category: {category!r}"}), 400
    if not jewel_file or not tag_file:
        return jsonify({"ok": False, "error": "missing category, front photo, or tag photo"}), 400

    result = ct.save_pair(category, jewel_file.read(), tag_file.read(), tag_code,
                          staff_name=staff_name, override_duplicate=override_duplicate,
                          override_blur=override_blur, override_visibility=override_visibility)
    return jsonify(result)


@app.route("/api/capture/save_multi", methods=["POST"])
def api_capture_save_multi():
    """RSC 2 3-angle capture set: MAIN + ANGLE_1 + ANGLE_2 -> <tag>.jpg /
    <tag>_1.jpg / <tag>_2.jpg (see capture_tool.save_multi). The tag photo
    itself is read client-side for its code only and never uploaded here —
    same contract as /api/capture/save's tag_code field."""
    import capture_tool as ct
    import ornament_code_map as ocm
    category = request.form.get("category", "")
    tag_code = request.form.get("tag_code", "")
    staff_name = request.form.get("staff_name", "")
    override_duplicate = request.form.get("override_duplicate") == "1"
    override_blur = request.form.get("override_blur") == "1"
    override_visibility = request.form.get("override_visibility") == "1"
    main_file = request.files.get("main")
    angle1_file = request.files.get("angle1")
    angle2_file = request.files.get("angle2")
    if not category and tag_code:
        auto = ocm.category_from_tag_code(tag_code)
        if auto:
            category = auto.key
    if not category or category not in ct.CATEGORY_LABELS:
        return jsonify({"ok": False, "error": f"missing or unknown category: {category!r}"}), 400
    if not main_file or not angle1_file or not angle2_file:
        return jsonify({"ok": False, "error": "missing main, angle1, or angle2 image"}), 400
    if not tag_code:
        return jsonify({"ok": False, "error": "tag_code is required for the multi-angle workflow"}), 400

    result = ct.save_multi(category, main_file.read(), angle1_file.read(), angle2_file.read(),
                           tag_code, staff_name=staff_name, override_duplicate=override_duplicate,
                           override_blur=override_blur, override_visibility=override_visibility)
    return jsonify(result)


def _run_spin_processing(video_path: str, output_dir: str, tag_stem: str) -> None:
    import spin_processor
    try:
        spin_processor.process_spin(video_path, output_dir, tag_stem)
    except Exception:
        import logging
        logging.getLogger("spin_processor").exception("Spin processing failed for %s", tag_stem)


@app.route("/api/capture/spin", methods=["POST"])
def api_capture_spin():
    """Saves a recorded turntable-rotation clip and kicks off local
    frame-extraction/cropping/360-viewer processing in the background --
    no AI credit spend involved, so the phone doesn't wait for it (see
    spin_processor.py's module docstring)."""
    import capture_tool as ct
    import ornament_code_map as ocm
    category = request.form.get("category", "")
    tag_code = request.form.get("tag_code", "")
    video_file = request.files.get("video")
    if not category and tag_code:
        auto = ocm.category_from_tag_code(tag_code)
        if auto:
            category = auto.key
    if not category or category not in ct.CATEGORY_LABELS:
        return jsonify({"ok": False, "error": f"missing or unknown category: {category!r}"}), 400
    if not tag_code or not video_file:
        return jsonify({"ok": False, "error": "missing tag_code or video"}), 400

    tray = ct.get_current_tray(category)
    tray_dir = os.path.join(ct.CAPTURE_ROOT, tray["folder"])
    os.makedirs(tray_dir, exist_ok=True)
    tag_stem = ct._safe_filename_from_tag(tag_code)
    ext = os.path.splitext(video_file.filename or "")[1] or ".webm"
    video_path = os.path.join(tray_dir, f"{tag_stem}_360{ext}")
    video_file.save(video_path)

    output_dir = os.path.join(OUTPUT, category)
    os.makedirs(output_dir, exist_ok=True)
    threading.Thread(
        target=_run_spin_processing, args=(video_path, output_dir, tag_stem), daemon=True,
    ).start()
    return jsonify({"ok": True, "processing": True})


@app.route("/api/heartbeat", methods=["POST"])
def api_heartbeat():
    return jsonify({"ok": True, "capture_version": _capture_page_version()})


@app.route("/api/health")
def api_health():
    """Deliberately shallow — capture doesn't use Copilot/Gemini/Codex at
    all, so there's nothing deep to check beyond 'can we write our data
    files'. Keeping this cheap and fast is itself part of the hardwall:
    the whole point of splitting this out was to stop a slow multi-engine
    health probe from ever being on capture's critical path again."""
    import capture_tool as ct
    try:
        probe = os.path.join(ct.CAPTURE_ROOT, ".health_probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        disk_ok = True
    except Exception:
        disk_ok = False
    return jsonify({"ok": disk_ok, "ts": time.time()})


@app.route("/static/<path:name>")
def static_files(name):
    return send_from_directory(os.path.join(BASE, "static"), name)


def _local_https_sans():
    sans = {"localhost", "127.0.0.1", "::1"}
    hostname = socket.gethostname().strip()
    if hostname:
        sans.add(hostname)
        sans.add(f"{hostname}.local")
    try:
        import psutil
        for addrs in psutil.net_if_addrs().values():
            for addr in addrs:
                if getattr(addr, "family", None) != socket.AF_INET:
                    continue
                ip = str(getattr(addr, "address", "") or "").strip()
                if not ip or ip.startswith("169.254.") or ip == "0.0.0.0":
                    continue
                sans.add(ip)
    except Exception:
        pass
    return sorted(sans)


def _load_https_meta():
    try:
        with open(_SSL_META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if isinstance(meta, dict) and isinstance(meta.get("sans"), list):
            return [str(item) for item in meta["sans"] if str(item).strip()]
    except Exception:
        pass
    return []


def _write_https_meta(sans):
    try:
        with open(_SSL_META_PATH, "w", encoding="utf-8") as f:
            json.dump({"sans": list(sans)}, f, indent=2)
    except Exception:
        pass


def _ensure_https_context():
    sans = _local_https_sans()
    if (os.path.exists(_SSL_CERT_PATH) and os.path.exists(_SSL_KEY_PATH)
            and _load_https_meta() == sans):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(_SSL_CERT_PATH, _SSL_KEY_PATH)
        return context

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JewelleryCatalogTool"),
        x509.NameAttribute(NameOID.COMMON_NAME, "JewelleryCatalogTool Capture"),
    ])
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    san_entries = []
    for item in sans:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(item)))
        except ValueError:
            san_entries.append(x509.DNSName(item))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    with open(_SSL_CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(_SSL_KEY_PATH, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    _write_https_meta(sans)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(_SSL_CERT_PATH, _SSL_KEY_PATH)
    return context


class _BoundedTimeoutRequestHandler(WSGIRequestHandler):
    """Root-cause fix for "capture stops working every now and then, phone
    restart fixes it": WSGIRequestHandler.timeout defaults to None, so a
    request whose connection stalls (phone walks out of Wi-Fi range mid
    photo-upload, a poor-signal corner of the shop, etc.) parks its
    server-side thread FOREVER — socketserver only enforces a timeout when
    the handler class sets one. threaded=True means each such stall costs
    one more permanently-blocked thread rather than crashing anything
    outright, so the tool doesn't die, it slowly accumulates zombies until
    it looks broken. Restarting the PHONE was never the actual fix — it just
    starts a fresh connection on a fresh thread, which succeeds immediately
    because Werkzeug's threaded server always has room for one more. The
    stuck threads from earlier stalls are very likely still there.

    90s is generous for a phone camera photo upload even on a poor
    connection, and is not on any path a legitimate request should ever
    approach — capture_server.py makes zero outbound network calls (see
    module docstring), so nothing here has a reason to run long.
    """
    timeout = 90


if __name__ == "__main__":
    from single_instance import enforce_single_instance
    enforce_single_instance("capture_server")
    port = PORT
    try:
        with open(os.path.join(BASE, "capture_port.txt"), "w") as f:
            f.write(str(port))
    except OSError:
        pass
    ssl_context = None
    try:
        ssl_context = _ensure_https_context()
        print(f"[{time.strftime('%H:%M:%S')}]  Capture Server (isolated)  ->  https://0.0.0.0:{port}  (LAN-reachable, login required)")
    except Exception as exc:
        print(f"[{time.strftime('%H:%M:%S')}]  HTTPS cert setup failed, falling back to HTTP: {exc}")
        print(f"[{time.strftime('%H:%M:%S')}]  Capture Server (isolated)  ->  http://0.0.0.0:{port}  (LAN-reachable, login required)")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True,
            request_handler=_BoundedTimeoutRequestHandler, ssl_context=ssl_context)
