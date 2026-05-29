import os
import sys
import time
import logging
import requests
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv

from layout_engine import create_full_page_layout, create_id_layout, is_image

# Load environment variables
load_dotenv()

CLOUD_SERVER_URL = os.getenv("CLOUD_SERVER_URL")
PRINTER_NAME = os.getenv("PRINTER_NAME")
SUMATRA_PATH = os.getenv("SUMATRA_PATH")

def setup_logging():
    log_dir = Path("logs")
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
    logging.info(f"Downloading file from {url} to {target_path}")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    with open(target_path, 'wb') as f:
        f.write(response.content)

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

def process_job(job):
    job_id = job.get("job_id")
    if not job_id:
        logging.error("Job missing job_id")
        return

    logging.info(f"Processing job {job_id}")

    try:
        # Mark status as printing locally
        job['status'] = 'printing'
        logging.info(f"Job {job_id} status marked as printing")

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
        resp = requests.post(
            f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/complete",
            timeout=10
        )
        resp.raise_for_status()

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Error processing job {job_id}: {error_msg}")
        try:
            resp = requests.post(
                f"{CLOUD_SERVER_URL}/api/agent/jobs/{job_id}/error",
                json={"error_message": error_msg},
                timeout=10
            )
            resp.raise_for_status()
        except Exception as api_err:
            logging.error(f"Failed to send error state for job {job_id}: {api_err}")

def main_loop():
    while True:
        try:
            logging.info("Polling for pending jobs...")
            resp = requests.get(
                f"{CLOUD_SERVER_URL}/api/agent/jobs/pending",
                timeout=10
            )
            resp.raise_for_status()
            jobs = resp.json()

            if not isinstance(jobs, list):
                logging.error(f"Expected a list of jobs, got {type(jobs).__name__}. Skipping cycle.")
            else:
                if jobs:
                    logging.info(f"Found {len(jobs)} pending jobs.")
                for job in jobs:
                    process_job(job)
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during polling: {e}")
        except Exception as e:
            logging.error(f"Unexpected error during polling cycle: {e}")

        time.sleep(5)

if __name__ == "__main__":
    setup_logging()
    validate_config()
    logging.info("Agent started.")
    main_loop()
