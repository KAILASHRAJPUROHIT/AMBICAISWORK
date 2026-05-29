import os
import time
import subprocess
import requests
import re
import logging
from pathlib import Path
from dotenv import load_dotenv
from pypdf import PdfReader

import local_db
import layout_engine

# Setup Logging
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "agent.log",
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()

CLOUD_SERVER_URL = os.getenv("CLOUD_SERVER_URL", "http://localhost:5000")
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "")
PRINTER_NAME = os.getenv("PRINTER_NAME", "")
SUMATRA_PATH = os.getenv("SUMATRA_PATH", "")
POLL_INTERVAL = 5
WORKSPACE_DIR = Path(__file__).parent / "AgentWorkspace"

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = WORKSPACE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)
PDF_DIR = WORKSPACE_DIR / "pdfs"
PDF_DIR.mkdir(exist_ok=True)

HEADERS = {"Authorization": f"Bearer {AGENT_TOKEN}"}

def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9_-]', '', str(name))

def cleanup_old_files(days=7):
    now = time.time()
    cutoff = now - (days * 86400)
    for directory in [TEMP_DIR, PDF_DIR]:
        for f in directory.glob("*"):
            if f.is_file() and f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                except OSError:
                    pass

def download_file(url, dest_path):
    temp_path = dest_path.with_suffix('.tmp')
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    temp_path.replace(dest_path)

def report_status(job_id, status, error_msg=""):
    try:
        payload = {"status": status, "error": error_msg}
        resp = requests.patch(f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/status", json=payload, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        logging.info(f"Reported {job_id} as {status}")
    except Exception as e:
        logging.error(f"Failed to report status for {job_id}: {e}")

def check_duplex(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        if len(reader.pages) == 2:
            return True
    except Exception as e:
        logging.warning(f"Failed to parse PDF pages for duplex check: {e}")
    return False

def process_job(job):
    raw_job_id = str(job["id"])
    job_id = sanitize_filename(raw_job_id)
    
    if not job_id:
        return

    # Idempotency Check
    local_status = local_db.get_job_status(job_id)
    if local_status == "PRINTED":
        report_status(job_id, "completed") # Sync cloud if it missed the update
        return

    # Mark printing
    local_db.set_job_status(job_id, "PENDING")
    report_status(job_id, "printing")
    logging.info(f"Processing job {job_id}")

    try:
        final_pdf_path = PDF_DIR / f"{job_id}.pdf"
        print_mode = job.get("print_mode", "auto")
        
        # Determine Routing based on mode and files
        if "pdf_url" in job and job["pdf_url"] and (print_mode == 'pdf' or print_mode == 'auto'):
            # Pure PDF pass-through
            download_file(job["pdf_url"], final_pdf_path)
        
        elif "image_urls" in job and job["image_urls"]:
            # ID Card / Image grouping
            local_images = []
            for idx, img_url in enumerate(job["image_urls"]):
                img_path = TEMP_DIR / f"{job_id}_{idx}.jpg"
                download_file(img_url, img_path)
                local_images.append(img_path)
            
            pairing = job.get("front_back_pairing", False)
            
            if print_mode == 'auto':
                classification = layout_engine.classify_image(local_images[0])
                if classification == "FULL_PAGE":
                    layout_engine.create_full_page_layout(local_images, final_pdf_path, TEMP_DIR)
                else:
                    layout_engine.create_id_layout(local_images, final_pdf_path, TEMP_DIR, pair_front_back=pairing)
            elif print_mode == 'pdf' or print_mode == 'full_page_pdf':
                layout_engine.create_full_page_layout(local_images, final_pdf_path, TEMP_DIR)
            else:
                layout_engine.create_id_layout(local_images, final_pdf_path, TEMP_DIR, pair_front_back=pairing)
        else:
            raise ValueError("No processable files found in payload.")

        local_db.set_job_status(job_id, "PENDING", str(final_pdf_path))

        # Setup Sumatra parameters
        if not Path(SUMATRA_PATH).exists():
            raise FileNotFoundError(f"SumatraPDF not found at {SUMATRA_PATH}")

        copies = job.get("copies", 1)
        # Enforce valid copies range
        if not isinstance(copies, int) or copies < 1 or copies > 5:
            copies = 1
            
        settings = f"{copies}x"
        
        # Duplex check logic
        if (print_mode == 'pdf' or print_mode == 'auto') and check_duplex(final_pdf_path):
            settings += ",duplex"

        cmd = [
            SUMATRA_PATH,
            "-print-to", PRINTER_NAME,
            "-print-settings", settings,
            "-silent",
            str(final_pdf_path)
        ]
        
        logging.info(f"Printing {job_id} with settings: {settings}")

        # 60s hard timeout to prevent deadlock
        subprocess.run(cmd, check=True, timeout=60)

        # Mark completed
        local_db.set_job_status(job_id, "PRINTED")
        report_status(job_id, "completed")
        logging.info(f"Job {job_id} successfully completed.")

    except subprocess.TimeoutExpired:
        local_db.set_job_status(job_id, "FAILED")
        msg = "Printer timed out (Possible paper jam or offline)."
        report_status(job_id, "failed", msg)
        logging.error(f"Job {job_id} timed out: {msg}")
    except Exception as e:
        local_db.set_job_status(job_id, "FAILED")
        report_status(job_id, "failed", str(e))
        logging.error(f"Job {job_id} failed: {e}")

def run_once():
    try:
        cleanup_old_files()
        
        resp = requests.get(f"{CLOUD_SERVER_URL}/api/agent/jobs/pending", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
        
        for job in jobs:
            process_job(job)
    except requests.exceptions.RequestException:
        pass # Silent network ignore
    except Exception as e:
        logging.error(f"Unexpected error in run_once: {e}")

def run_forever():
    local_db.init_db()
    logging.info("Aradhana Print Agent started. Polling for jobs...")
    while True:
        run_once()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_forever()
