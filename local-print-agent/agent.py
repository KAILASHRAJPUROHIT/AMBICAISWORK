import os
import sys
import time
import logging
import traceback
import requests
import subprocess
import tempfile
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

# Self-healing: a job that fails (e.g. a transient network blip while
# downloading files, or a momentary spooler hiccup) is retried automatically
# instead of sitting in "failed" until a human clicks Retry in /admin.
MAX_JOB_ATTEMPTS = 3
JOB_RETRY_BACKOFF_SECONDS = [10, 30, 60]  # delay after attempt 1, 2, 3 fails
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_RETRY_BACKOFF_SECONDS = [5, 15, 30]

# Printer targeting: the admin panel's selected default printer (reported via
# /api/agent/printers, returned to us in every /api/agent/jobs/pending poll)
# is the source of truth once an admin has set one in /admin. PRINTER_NAME
# from .env is only a fallback for as long as nobody has opened /admin yet.
# See process_job/print_pdf for the enforcement that makes this an actual
# guarantee, not just a default — this is what stops a job from silently
# landing on a second, stale, or mistyped printer.
_LAST_KNOWN_PRINTERS = []
PRINTER_REPORT_EVERY_N_POLLS = 12  # ~60s at the 5s poll interval below


def _notify(title, body=""):
    try:
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command",
             f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null;"
             f"$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
             f"$t.GetElementsByTagName('text')[0].AppendChild($t.CreateTextNode('{title}')) | Out-Null;"
             f"$t.GetElementsByTagName('text')[1].AppendChild($t.CreateTextNode('{body}')) | Out-Null;"
             f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Aradhana Print').Show([Windows.UI.Notifications.ToastNotification]::new($t))"],
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

    if missing:
        logging.critical(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    # PRINTER_NAME is now optional — the admin panel's default-printer
    # selection (see process_job) is the primary path. .env's PRINTER_NAME
    # only matters as a fallback for as long as nobody has opened /admin yet.
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
            timeout=10,
        ).raise_for_status()
        logging.info(f"Reported {len(printers)} local printer(s) to server: {', '.join(printers)}")
    except Exception as e:
        logging.warning(f"Failed to report printers to server: {e}")


def download_file(url, target_path):
    last_error = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            logging.info(f"Downloading file from {url} to {target_path} (attempt {attempt}/{DOWNLOAD_ATTEMPTS})")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            with open(target_path, 'wb') as f:
                f.write(response.content)
            return
        except Exception as e:
            last_error = e
            logging.warning(f"Download attempt {attempt}/{DOWNLOAD_ATTEMPTS} failed: {e}")
            if attempt < DOWNLOAD_ATTEMPTS:
                time.sleep(DOWNLOAD_RETRY_BACKOFF_SECONDS[attempt - 1])
    raise last_error

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

def _attempt_job(job, job_id, printer_name):
    """One end-to-end attempt at a job: mark printing, download, render, print,
    mark completed. Raises on any failure — the caller decides whether to
    retry or give up."""
    job['status'] = 'printing'
    logging.info(f"Job {job_id} status marked as printing")
    requests.patch(
        f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/status",
        json={"status": "printing"},
        timeout=10
    ).raise_for_status()

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

    # Post success
    logging.info(f"Job {job_id} completed successfully. Notifying server.")
    resp = requests.patch(
        f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/status",
        json={"status": "completed"},
        timeout=10
    )
    resp.raise_for_status()
    _notify(f"Printed: {job_id}", f"{print_mode} · {copies} cop{'y' if copies==1 else 'ies'}")


def process_job(job, printer_name):
    job_id = job.get("job_id")
    if not job_id:
        logging.error("Job missing job_id")
        return

    logging.info(f"Processing job {job_id}")

    # Hard gate: never print anywhere unless we know exactly where. No
    # silent fallback to the OS's default printer — that ambiguity is
    # exactly what let a job land on the wrong device before.
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
                timeout=10,
            ).raise_for_status()
        except Exception as api_err:
            logging.error(f"Could not report printer-mismatch hold for {job_id}: {api_err}")
        return

    last_error_msg = None
    for attempt in range(1, MAX_JOB_ATTEMPTS + 1):
        try:
            _attempt_job(job, job_id, printer_name)
            return  # success — nothing more to do
        except Exception:
            last_error_msg = traceback.format_exc()
            logging.error(
                f"Job {job_id} attempt {attempt}/{MAX_JOB_ATTEMPTS} failed:\n{last_error_msg}"
            )
            if attempt < MAX_JOB_ATTEMPTS:
                delay = JOB_RETRY_BACKOFF_SECONDS[attempt - 1]
                logging.info(f"Retrying job {job_id} in {delay}s (self-healing)…")
                time.sleep(delay)

    # All attempts exhausted — report failure to the server for human review.
    logging.error(f"Job {job_id} failed after {MAX_JOB_ATTEMPTS} attempts. Giving up.")
    try:
        resp = requests.patch(
            f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/status",
            json={"status": "failed", "error": last_error_msg[:2000]},
            timeout=10
        )
        resp.raise_for_status()
    except Exception as api_err:
        logging.error(f"Failed to send error state for job {job_id}: {api_err}")

POLL_INTERVAL_SECONDS = 5
MAX_POLL_BACKOFF_SECONDS = 60


def main_loop():
    consecutive_poll_failures = 0
    poll_count = 0
    while True:
        try:
            if poll_count % PRINTER_REPORT_EVERY_N_POLLS == 0:
                report_printers()
            poll_count += 1

            logging.info("Polling for pending jobs...")
            resp = requests.get(
                f"{CLOUD_SERVER_URL}/api/agent/jobs/pending",
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            consecutive_poll_failures = 0

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
            consecutive_poll_failures += 1
            logging.error(f"Network error during polling (failure #{consecutive_poll_failures}): {e}")
        except Exception as e:
            consecutive_poll_failures += 1
            logging.error(f"Unexpected error during polling cycle (failure #{consecutive_poll_failures}): {e}")

        if consecutive_poll_failures:
            # Self-healing backoff: don't hammer an unreachable server —
            # back off up to MAX_POLL_BACKOFF_SECONDS, then keep retrying at
            # that cadence until it recovers, at which point normal 5s
            # polling resumes automatically (consecutive_poll_failures resets
            # to 0 above on the next successful poll).
            delay = min(POLL_INTERVAL_SECONDS * (2 ** (consecutive_poll_failures - 1)), MAX_POLL_BACKOFF_SECONDS)
        else:
            delay = POLL_INTERVAL_SECONDS
        time.sleep(delay)

if __name__ == "__main__":
    setup_logging()
    validate_config()
    logging.info("Agent started.")
    main_loop()
