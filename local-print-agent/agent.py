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
    if not PRINTER_NAME:
        missing.append("PRINTER_NAME")
    if not SUMATRA_PATH:
        missing.append("SUMATRA_PATH")
    
    if missing:
        logging.critical(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

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

def print_pdf(pdf_path):
    logging.info(f"Printing PDF: {pdf_path}")
    command = [
        SUMATRA_PATH,
        "-print-to", PRINTER_NAME,
        "-silent",
        str(pdf_path)
    ]
    logging.info(f"Executing print command: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Print command failed with exit code {result.returncode}: {result.stderr}")
    logging.info("Print command executed successfully")

def _attempt_job(job, job_id):
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
                    print_pdf(output_pdf)
            else:
                logging.info("Printing original PDF file(s)")
                for pdf_file in downloaded_files:
                    for _ in range(copies):
                        print_pdf(pdf_file)

        elif print_mode == "id_card":
            logging.info("Generating ID card layout PDF")
            create_id_layout(downloaded_files, output_pdf, temp_dir_path)
            for _ in range(copies):
                print_pdf(output_pdf)
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


def process_job(job):
    job_id = job.get("job_id")
    if not job_id:
        logging.error("Job missing job_id")
        return

    logging.info(f"Processing job {job_id}")

    last_error_msg = None
    for attempt in range(1, MAX_JOB_ATTEMPTS + 1):
        try:
            _attempt_job(job, job_id)
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
    while True:
        try:
            logging.info("Polling for pending jobs...")
            resp = requests.get(
                f"{CLOUD_SERVER_URL}/api/agent/jobs/pending",
                timeout=10
            )
            resp.raise_for_status()
            jobs = resp.json()
            consecutive_poll_failures = 0

            if not isinstance(jobs, list):
                logging.error(f"Expected a list of jobs, got {type(jobs).__name__}. Skipping cycle.")
            else:
                if jobs:
                    logging.info(f"Found {len(jobs)} pending jobs.")
                for job in jobs:
                    process_job(job)
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
