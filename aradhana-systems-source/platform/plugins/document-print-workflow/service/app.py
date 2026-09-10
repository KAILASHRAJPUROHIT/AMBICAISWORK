"""AIS Document Print Workflow API. LAN-only deployment adapter belongs above this module."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("AIS_DOCUMENT_WORKFLOW_DB", ROOT / "document_workflow.db"))
WAIT_SECONDS = 60
VALID_DECISIONS = {"attach", "standalone", "bill_only", "wait"}

app = Flask(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def expire_stale_bundles(db: sqlite3.Connection) -> None:
    """Keep the local selection list aligned with the cloud's 30-minute hold."""
    db.execute("UPDATE document_bundles SET status='expired' WHERE status='pending' AND created_at < ?",
               (stamp(utcnow() - timedelta(minutes=30)),))


def stamp(value: datetime | None = None) -> str:
    return (value or utcnow()).isoformat()


@contextmanager
def database():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with database() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS document_bundles (
          id TEXT PRIMARY KEY, display_name TEXT NOT NULL, status TEXT NOT NULL,
          created_at TEXT NOT NULL, armed_session_id TEXT, checksum TEXT
        );
        CREATE TABLE IF NOT EXISTS print_sessions (
          id TEXT PRIMARY KEY, customer_name TEXT, bill_reference TEXT,
          status TEXT NOT NULL, decision TEXT, bundle_id TEXT,
          wait_until TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events (
          id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
          action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """)


@app.get("/health")
def health():
    try:
        with database() as db:
            expire_stale_bundles(db)
            pending = db.execute("SELECT COUNT(*) FROM document_bundles WHERE status='pending'").fetchone()[0]
            waiting = db.execute("SELECT COUNT(*) FROM print_sessions WHERE status='waiting_for_scan'").fetchone()[0]
        return jsonify(status="healthy", pending_bundles=pending, waiting_sessions=waiting)
    except sqlite3.Error as error:
        return jsonify(status="unhealthy", error=str(error)), 503


def audit(db: sqlite3.Connection, entity_type: str, entity_id: str, action: str, detail: dict) -> None:
    db.execute(
        "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), entity_type, entity_id, action, json.dumps(detail, sort_keys=True), stamp()),
    )


def session_view(row: sqlite3.Row) -> dict:
    result = dict(row)
    if row["decision"] == "wait" and row["wait_until"]:
        expired = utcnow() >= datetime.fromisoformat(row["wait_until"])
        result["wait_expired"] = expired
        result["recommended_action"] = "bill_only" if expired else "wait"
    return result


@app.post("/api/v1/document-bundles")
def create_bundle():
    data = request.get_json(silent=True) or {}
    display_name = str(data.get("display_name") or "Pending ID documents").strip()
    if not display_name:
        return jsonify(error="display_name is required"), 400
    requested_id = str(data.get("bundle_id") or "").strip().upper()
    bundle_id = requested_id or ("DOC-" + uuid.uuid4().hex[:12].upper())
    if not bundle_id.startswith("DOC-") or len(bundle_id) > 64:
        return jsonify(error="invalid bundle_id"), 400
    with database() as db:
        expire_stale_bundles(db)
        existing = db.execute("SELECT * FROM document_bundles WHERE id=?", (bundle_id,)).fetchone()
        if existing:
            # Cloud OCR may refine a generic queue label after the initial sync.
            # This is display metadata only; it never arms, attaches, or prints.
            # A previous local selection is only provisional until the cloud
            # bundle is claimed. If the cloud still lists it, make it visible
            # again so a transient network failure cannot hide it for 30 min.
            if existing["status"] == "armed":
                db.execute("UPDATE document_bundles SET status='pending', armed_session_id=NULL WHERE id=?", (bundle_id,))
            if existing["status"] == "pending" and existing["display_name"] != display_name[:120]:
                db.execute("UPDATE document_bundles SET display_name=? WHERE id=?", (display_name[:120], bundle_id))
                audit(db, "document_bundle", bundle_id, "display_name_updated", {"display_name": display_name[:120]})
            current = db.execute("SELECT status FROM document_bundles WHERE id=?", (bundle_id,)).fetchone()["status"]
            return jsonify(id=bundle_id, status=current, existing=True), 200
        source_created_at = str(data.get("created_at") or stamp())
        # Source timestamp controls the 30-minute biller window. Invalid values
        # fall back to receipt time rather than breaking document visibility.
        try:
            datetime.fromisoformat(source_created_at.replace("Z", "+00:00"))
        except ValueError:
            source_created_at = stamp()
        db.execute("INSERT INTO document_bundles VALUES (?, ?, 'pending', ?, NULL, ?)",
                   (bundle_id, display_name[:120], source_created_at, data.get("checksum")))
        audit(db, "document_bundle", bundle_id, "created", {"display_name": display_name[:120]})
    return jsonify(id=bundle_id, status="pending"), 201


@app.get("/api/v1/document-bundles")
def list_bundles():
    with database() as db:
        expire_stale_bundles(db)
        rows = db.execute("SELECT * FROM document_bundles WHERE status='pending' ORDER BY created_at DESC").fetchall()
    return jsonify(bundles=[dict(row) for row in rows])


@app.post("/api/v1/document-bundles/reconcile")
def reconcile_bundles():
    """Hide local choices that the authoritative QR queue no longer offers."""
    data = request.get_json(silent=True) or {}
    supplied = data.get("bundle_ids", [])
    if not isinstance(supplied, list) or not all(isinstance(value, str) for value in supplied):
        return jsonify(error="bundle_ids must be a list of strings"), 400
    active = {value.strip().upper() for value in supplied if value.strip()}
    with database() as db:
        expire_stale_bundles(db)
        rows = db.execute("SELECT id FROM document_bundles WHERE status IN ('pending', 'armed')").fetchall()
        removed = [row["id"] for row in rows if row["id"] not in active]
        for bundle_id in removed:
            db.execute("UPDATE document_bundles SET status='removed', armed_session_id=NULL WHERE id=?", (bundle_id,))
            audit(db, "document_bundle", bundle_id, "reconciled_removed", {})
    return jsonify(removed=len(removed), active=len(active))


@app.post("/api/v1/print-sessions")
def create_print_session():
    data = request.get_json(silent=True) or {}
    session_id = "PRINT-" + uuid.uuid4().hex[:12].upper()
    customer = str(data.get("customer_name") or "").strip()[:120]
    bill_ref = str(data.get("bill_reference") or "").strip()[:120]
    now = stamp()
    with database() as db:
        db.execute("INSERT INTO print_sessions VALUES (?, ?, ?, 'awaiting_decision', NULL, NULL, NULL, ?, ?)",
                   (session_id, customer, bill_ref, now, now))
        audit(db, "print_session", session_id, "opened", {"customer_name": customer, "bill_reference": bill_ref})
    # `wait` remains accepted by the API for a prior staged Router build.
    # Current AIS UI deliberately exposes only attach, explicit document print,
    # and dismiss: normal Ornate printing is never a workflow command.
    return jsonify(id=session_id, status="awaiting_decision", options=["attach", "standalone", "bill_only"]), 201


@app.post("/api/v1/print-sessions/<session_id>/decision")
def decide_print_session(session_id: str):
    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    bundle_id = data.get("bundle_id")
    if decision not in VALID_DECISIONS:
        return jsonify(error="invalid decision"), 400
    with database() as db:
        session = db.execute("SELECT * FROM print_sessions WHERE id=?", (session_id,)).fetchone()
        if not session:
            return jsonify(error="print session not found"), 404
        if decision == "attach":
            bundle = db.execute("SELECT * FROM document_bundles WHERE id=? AND status='pending'", (bundle_id,)).fetchone()
            if not bundle:
                return jsonify(error="select a pending document bundle"), 409
            db.execute("UPDATE document_bundles SET status='armed', armed_session_id=? WHERE id=?", (session_id, bundle_id))
        wait_until = stamp(utcnow() + timedelta(seconds=WAIT_SECONDS)) if decision == "wait" else None
        state = "waiting_for_scan" if decision == "wait" else "decided"
        db.execute("UPDATE print_sessions SET status=?, decision=?, bundle_id=?, wait_until=?, updated_at=? WHERE id=?",
                   (state, decision, bundle_id if decision == "attach" else None, wait_until, stamp(), session_id))
        audit(db, "print_session", session_id, "decision", {"decision": decision, "bundle_id": bundle_id, "wait_until": wait_until})
        row = db.execute("SELECT * FROM print_sessions WHERE id=?", (session_id,)).fetchone()
    return jsonify(session_view(row))


@app.get("/api/v1/print-sessions/<session_id>")
def get_print_session(session_id: str):
    with database() as db:
        row = db.execute("SELECT * FROM print_sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        return jsonify(error="print session not found"), 404
    return jsonify(session_view(row))


@app.post("/api/v1/print-sessions/<session_id>/outcome")
def record_print_outcome(session_id: str):
    data = request.get_json(silent=True) or {}
    outcome = data.get("outcome")
    if outcome not in {"spooled", "failed"}:
        return jsonify(error="outcome must be spooled or failed"), 400
    with database() as db:
        row = db.execute("SELECT * FROM print_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return jsonify(error="print session not found"), 404
        db.execute("UPDATE print_sessions SET status=?, updated_at=? WHERE id=?",
                   ("spooled" if outcome == "spooled" else "print_failed", stamp(), session_id))
        audit(db, "print_session", session_id, "physical_print_" + outcome, {"detail": str(data.get("detail") or "")[:500]})
    return jsonify(id=session_id, status="spooled" if outcome == "spooled" else "print_failed")


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.environ.get("AIS_DOCUMENT_WORKFLOW_PORT", "8310")))
