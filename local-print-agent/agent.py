def run_once():
    try:
        cleanup_old_files()

        resp = requests.get(
            f"{CLOUD_SERVER_URL}/api/agent/jobs/pending",
            headers=HEADERS,
            timeout=10
        )

        resp.raise_for_status()

        data = resp.json()

        # Support both old and new API formats
        if isinstance(data, list):
            jobs = data
        elif isinstance(data, dict):
            jobs = data.get("jobs", [])
        else:
            jobs = []

        logging.info(f"Found {len(jobs)} pending jobs")

        for job in jobs:
            process_job(job)

    except requests.exceptions.RequestException as e:
        logging.error(f"Network error: {e}")

    except Exception as e:
        logging.error(f"Unexpected error in run_once: {e}")