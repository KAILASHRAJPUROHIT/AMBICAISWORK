import os
import time
import subprocess
import requests
import re
from pathlib import Path
from dotenv import load_dotenv

import local_db
import layout

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:5000")
API_TOKEN = os.getenv("API_TOKEN", "")
PRINTER_NAME = os.getenv("PRINTER_NAME", "")
SUMATRA_PATH = os.getenv("SUMATRA_PATH", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "C:/WhatsappAutoPrint/AgentWorkspace"))

# Ensure workspace exists
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = WORKSPACE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)
PDF_DIR = WORKSPACE_DIR / "pdfs"
PDF_DIR.mkdir(exist_ok=True)

HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

def sanitize_filename(name):
    """Prevent Path Traversal by enforcing alphanumeric/dash/underscore only."""
    return re.sub(r'[^a-zA-Z0-9_-]', '', str(name))

def cleanup_old_files(days=7):
    """Prevent Storage Exhaustion by deleting old files."""
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
    """Download with atomic renaming to prevent corrupted files on network drop."""
    temp_path = dest_path.with_suffix('.tmp')
    
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    
    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            
    # Atomic replace
    temp_path.replace(dest_path)

def report_status(job_id, status, error_msg=""):
    try:
        payload = {"status": status, "error": error_msg}
        resp = requests.patch(f"{API_URL}/api/agent/jobs/{job_id}/status", json=payload, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Failed to report status for {job_id}: {e}")

def process_job(job):
    raw_job_id = str(job["id"])
    job_id = sanitize_filename(raw_job_id)
    
    if not job_id:
        print("Invalid job_id received.")
        return

    # 1. Idempotency Check
    local_status = local_db.get_job_status(job_id)
    if local_status == "PRINTED":
        report_status(job_id, "completed")
        return

    # 2. Mark Local as Pending
    local_db.set_job_status(job_id, "PENDING")
    report_status(job_id, "printing")

    try:
        pdf_path = PDF_DIR / f"{job_id}.pdf"
        
        if "pdf_url" in job and job["pdf_url"]:
            download_file(job["pdf_url"], pdf_path)
            
        elif "image_urls" in job and job["image_urls"]:
            local_images = []
            for idx, img_url in enumerate(job["image_urls"]):
                # Use sanitized job_id for temp images too
                img_path = TEMP_DIR / f"{job_id}_{idx}.jpg"
                download_file(img_url, img_path)
                local_images.append(img_path)
            
            layout.create_layout_pdf(local_images, pdf_path, TEMP_DIR)
        else:
            raise ValueError("No pdf_url or image_urls in job payload")

        local_db.set_job_status(job_id, "PENDING", str(pdf_path))

        # 3. Print (With Timeout to prevent deadlocks)
        if not Path(SUMATRA_PATH).exists():
            raise FileNotFoundError(f"SumatraPDF not found at {SUMATRA_PATH}")

        subprocess.run([
            SUMATRA_PATH,
            "-print-to", PRINTER_NAME,
            "-silent",
            str(pdf_path)
        ], check=True, timeout=60) # 60 second hard timeout

        # 4. Mark Completed
        local_db.set_job_status(job_id, "PRINTED")
        report_status(job_id, "completed")

    except subprocess.TimeoutExpired:
        local_db.set_job_status(job_id, "FAILED")
        report_status(job_id, "failed", "Printer timed out (Possible paper jam or offline).")
        print(f"Job {job_id} timed out at the printer.")
    except Exception as e:
        local_db.set_job_status(job_id, "FAILED")
        report_status(job_id, "failed", str(e))
        print(f"Job {job_id} failed: {e}")

def run_once():
    try:
        cleanup_old_files() # Run garbage collection
        
        resp = requests.get(f"{API_URL}/api/agent/jobs/pending", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
        
        for job in jobs:
            process_job(job)
    except requests.exceptions.RequestException as e:
        pass
    except Exception as e:
        print(f"Unexpected error in run_once: {e}")

def run_forever():
    local_db.init_db()
    print("Agent started. Polling for jobs...")
    while True:
        run_once()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_forever()
