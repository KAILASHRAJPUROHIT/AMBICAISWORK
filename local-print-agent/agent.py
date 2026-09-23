import os
import sys
import time
import logging
import traceback
import requests
import subprocess
import tempfile
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

from layout_engine import create_full_page_layout, create_id_layout, is_image

SCRIPT_DIR = Path(__file__).resolve().parent

# Load environment variables (absolute path — a Windows Service's working
# directory is not the script folder, so a bare load_dotenv() finds nothing)
load_dotenv(SCRIPT_DIR / ".env")

CLOUD_SERVER_URL = os.getenv("CLOUD_SERVER_URL")
PRINTER_NAME = os.getenv("PRINTER_NAME")
SUMATRA_PATH = os.getenv("SUMATRA_PATH")
TENANT_SLUG = os.getenv("TENANT_SLUG")
AGENT_API_KEY = os.getenv("AGENT_API_KEY")
AGENT_HEADERS = {"X-Agent-Key": AGENT_API_KEY or ""}
LEDGER_PATH = SCRIPT_DIR / "agent_state.db"

# Printer targeting: the admin panel's selected default printer (reported
# via /api/agent/printers, returned to us in every /api/agent/jobs/pending
# poll) is the source of truth once an admin has set one. PRINTER_NAME from
# .env is only a fallback for tenants that haven't opened /admin yet. See
# process_job/print_pdf for the enforcement that makes this an actual
# guarantee, not just a default.
_LAST_KNOWN_PRINTERS = []
PRINTER_REPORT_EVERY_N_POLLS = 12  # ~60s at the 5s poll interval below


def init_ledger():
    """Create the durable local execution ledger used to prevent reprints."""
    with sqlite3.connect(LEDGER_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_executions (
                job_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                detail TEXT
            )
            """
        )


def ledger_state(job_id):
    with sqlite3.connect(LEDGER_PATH) as conn:
        row = conn.execute(
            "SELECT state FROM job_executions WHERE job_id = ?", (job_id,)
        ).fetchone()
    return row[0] if row else None


def record_ledger(job_id, state, detail=""):
    with sqlite3.connect(LEDGER_PATH) as conn:
        conn.execute(
            """
            INSERT INTO job_executions (job_id, state, updated_at, detail)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                state = excluded.state,
                updated_at = excluded.updated_at,
                detail = excluded.detail
            """,
            (job_id, state, datetime.now(timezone.utc).isoformat(), detail[:2000]),
        )


def _notify(title, body=""):
    try:
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command",
             f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null;"
             f"$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
             f"$t.GetElementsByTagName('text')[0].AppendChild($t.CreateTextNode('{title}')) | Out-Null;"
             f"$t.GetElementsByTagName('text')[1].AppendChild($t.CreateTextNode('{body}')) | Out-Null;"
             f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('AMBIC SmartQR Print Agent').Show([Windows.UI.Notifications.ToastNotification]::new($t))"],
            creationflags=0x08000000
        )
    except Exception:
        pass


def setup_logging():
    log_dir = SCRIPT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove any existing handlers to prevent duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # File handler
    file_handler = logging.FileHandler(log_dir / "agent.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

def validate_config():
    missing = []
    if not CLOUD_SERVER_URL:
        missing.append("CLOUD_SERVER_URL")
    if not SUMATRA_PATH:
        missing.append("SUMATRA_PATH")
    if not TENANT_SLUG:
        missing.append("TENANT_SLUG")
    if not AGENT_API_KEY:
        missing.append("AGENT_API_KEY")

    if missing:
        logging.critical(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    # PRINTER_NAME is now optional here — the admin panel's default-printer
    # selection (see process_job) is the primary path. .env's PRINTER_NAME
    # only matters as a fallback for a tenant that hasn't opened /admin yet.
    if not PRINTER_NAME:
        logging.warning(
            "PRINTER_NAME not set in .env — this agent will only print once "
            "a default printer is selected in the admin panel."
        )

def list_local_printers():
    """Enumerates this Windows PC's installed printers via PowerShell (same
    shell-out pattern already used for toast notifications — no extra
    binary dependency). Returns [] on any failure rather than raising, since
    a transient enumeration failure shouldn't crash the poll loop."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Printer | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            logging.warning(f"Could not list local printers: {result.stderr.strip()}")
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception as e:
        logging.warning(f"Could not list local printers: {e}")
        return []


def report_printers():
    """Sends this PC's printer list to the cloud server so the admin panel
    can offer a real dropdown instead of free-text entry, and caches it
    locally so process_job can double-check a job's target printer still
    actually exists before printing."""
    global _LAST_KNOWN_PRINTERS
    printers = list_local_printers()
    if not printers:
        return
    _LAST_KNOWN_PRINTERS = printers
    try:
        requests.post(
            f"{CLOUD_SERVER_URL}/api/agent/printers",
            json={"printers": printers},
            headers=AGENT_HEADERS,
            timeout=10,
        ).raise_for_status()
        logging.info(f"Reported {len(printers)} local printer(s) to server: {', '.join(printers)}")
    except Exception as e:
        logging.warning(f"Failed to report printers to server: {e}")


def download_file(url, target_path):
    logging.info(f"Downloading file from {url} to {target_path}")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    with open(target_path, 'wb') as f:
        f.write(response.content)

def print_pdf(pdf_path, printer_name):
    logging.info(f"Printing PDF: {pdf_path} -> printer '{printer_name}'")
    command = [
        SUMATRA_PATH,
        "-print-to", printer_name,
        "-silent",
        str(pdf_path)
    ]
    logging.info(f"Executing print command: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Print command failed with exit code {result.returncode}: {result.stderr}")
    logging.info("Print command executed successfully")

def process_job(job, printer_name):
    job_id = job.get("job_id")
    if not job_id:
        logging.error("Job missing job_id")
        return

    logging.info(f"Processing job {job_id}")

    # Hard gate: never print anywhere unless we know exactly where. No
    # silent fallback to the OS's default printer — that's precisely the
    # kind of ambiguity that lets a job land on the wrong device.
    if not printer_name:
        message = (
            "No default printer configured for this job. Set one in the "
            "admin panel (Printer section) — or PRINTER_NAME in .env as a "
            "fallback — before this agent can print."
        )
        logging.critical(message)
        _notify("Print blocked — no printer set", job_id)
        try:
            requests.patch(
                f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/status",
                json={"status": "failed", "error": message},
                headers=AGENT_HEADERS,
                timeout=10,
            ).raise_for_status()
        except Exception as api_err:
            logging.error(f"Could not report missing-printer hold for {job_id}: {api_err}")
        return

    # Refuse to print to a name that doesn't match anything this PC has ever
    # actually reported as installed — catches a stale/renamed/mistyped
    # printer instead of letting Sumatra do something unpredictable with it.
    # Only enforced when we have positive knowledge of the local printer
    # list (an enumeration hiccup shouldn't brick an otherwise-working agent).
    if _LAST_KNOWN_PRINTERS and printer_name not in _LAST_KNOWN_PRINTERS:
        message = (
            f"Configured printer '{printer_name}' does not match any of this "
            f"PC's currently installed printers ({', '.join(_LAST_KNOWN_PRINTERS)}). "
            "Refusing to print rather than risk sending the job to the wrong device."
        )
        logging.critical(message)
        _notify("Print blocked — printer mismatch", job_id)
        try:
            requests.patch(
                f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/status",
                json={"status": "failed", "error": message},
                headers=AGENT_HEADERS,
                timeout=10,
            ).raise_for_status()
        except Exception as api_err:
            logging.error(f"Could not report printer-mismatch hold for {job_id}: {api_err}")
        return

    previous_state = ledger_state(job_id)
    if previous_state in {"printing", "printed", "completed"}:
        message = (
            f"Refusing to reprint {job_id}: local ledger state is "
            f"{previous_state}. Manual operator review required."
        )
        logging.critical(message)
        _notify("Print held for review", f"{job_id} may already have printed")
        try:
            requests.patch(
                f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/status",
                json={"status": "failed", "error": message},
                headers=AGENT_HEADERS,
                timeout=10,
            ).raise_for_status()
        except Exception as api_err:
            logging.error(f"Could not report duplicate-print hold for {job_id}: {api_err}")
        return

    try:
        # Mark status as printing locally and on server
        job['status'] = 'printing'
        logging.info(f"Job {job_id} status marked as printing")
        requests.patch(
            f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/status",
            json={"status": "printing"},
            headers=AGENT_HEADERS,
            timeout=10
        ).raise_for_status()
        record_ledger(job_id, "printing")

        files = job.get("files", [])
        if not files:
            raise Exception("No files provided in the job")

        print_mode = job.get("print_mode")
        copies = job.get("copies", 1)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            downloaded_files = []
            
            # Download all files
            for idx, file_info in enumerate(files):
                url = file_info.get("url")
                if not url:
                    raise Exception(f"File object missing URL at index {idx}")
                
                filename = file_info.get("filename", f"file_{idx}")
                target_path = temp_dir_path / filename
                download_file(url, target_path)
                downloaded_files.append(target_path)

            output_pdf = temp_dir_path / f"output_{job_id}.pdf"

            if print_mode == "pdf":
                # Check if all downloaded files are images
                all_images = all(is_image(f) for f in downloaded_files)
                if all_images:
                    logging.info("Converting image(s) to A4 PDF")
                    create_full_page_layout(downloaded_files, output_pdf, temp_dir_path)
                    for _ in range(copies):
                        print_pdf(output_pdf, printer_name)
                else:
                    logging.info("Printing original PDF file(s)")
                    for pdf_file in downloaded_files:
                        for _ in range(copies):
                            print_pdf(pdf_file, printer_name)

            elif print_mode == "id_card":
                logging.info("Generating ID card layout PDF")
                create_id_layout(downloaded_files, output_pdf, temp_dir_path)
                for _ in range(copies):
                    print_pdf(output_pdf, printer_name)
            else:
                raise Exception(f"Unsupported print_mode: {print_mode}")

        # Sumatra returned successfully for every requested copy. Persist this
        # before the server callback so a network failure cannot cause an
        # operator requeue to print the document twice.
        record_ledger(job_id, "printed")

        # Post success
        logging.info(f"Job {job_id} completed successfully. Notifying server.")
        resp = requests.patch(
            f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/status",
            json={"status": "completed"},
            headers=AGENT_HEADERS,
            timeout=10
        )
        resp.raise_for_status()
        record_ledger(job_id, "completed")
        _notify(f"Printed: {job_id}", f"{print_mode} · {copies} cop{'y' if copies==1 else 'ies'}")

    except Exception as e:
        error_msg = traceback.format_exc()
        logging.error(f"Error processing job {job_id}:\n{error_msg}")
        if ledger_state(job_id) != "printed":
            record_ledger(job_id, "failed", error_msg)
        try:
            resp = requests.patch(
                f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/status",
                json={"status": "failed", "error": error_msg[:2000]},
                headers=AGENT_HEADERS,
                timeout=10
            )
            resp.raise_for_status()
        except Exception as api_err:
            logging.error(f"Failed to send error state for job {job_id}: {api_err}")

def main_loop():
    poll_count = 0
    while True:
        try:
            if poll_count % PRINTER_REPORT_EVERY_N_POLLS == 0:
                report_printers()
            poll_count += 1

            logging.info("Polling for pending jobs...")
            resp = requests.get(
                f"{CLOUD_SERVER_URL}/api/agent/jobs/pending",
                headers=AGENT_HEADERS,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, list):
                # Older server without printer_name support — fall back to
                # the .env printer entirely.
                jobs, printer_name = data, PRINTER_NAME
            elif isinstance(data, dict):
                jobs = data.get("jobs", [])
                printer_name = data.get("printer_name") or PRINTER_NAME
            else:
                logging.error(f"Unexpected response shape from /api/agent/jobs/pending: {type(data).__name__}. Skipping cycle.")
                jobs, printer_name = [], None

            if jobs:
                logging.info(f"Found {len(jobs)} pending jobs. Printer: '{printer_name}'")
            for job in jobs:
                process_job(job, printer_name)
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during polling: {e}")
        except Exception as e:
            logging.error(f"Unexpected error during polling cycle: {e}")

        time.sleep(5)

if __name__ == "__main__":
    setup_logging()
    validate_config()
    init_ledger()
    logging.info("Agent started.")
    main_loop()
