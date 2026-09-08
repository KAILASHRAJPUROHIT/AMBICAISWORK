"""Keeps the local KYC-OCR vision model asleep by default, warming it just
before it's likely to be needed and putting it back to sleep afterward.

Policy:
  - Poll the QR print server's cloud warm-up signal every POLL_INTERVAL_SECONDS.
    That signal is a timestamp set the moment any device loads /print --
    chosen deliberately over a narrower "upload started" trigger, since page
    load happens earliest in the real flow and gives the most margin to
    absorb a cold model load before OCR is actually needed (see
    kyc-ocr-warmup design discussion, 2026-09-04).
  - If the signal is fresh and the model isn't already loaded, warm it.
  - If the model has been warm for longer than IDLE_TIMEOUT_SECONDS with no
    OCR having happened, sleep it anyway -- a safety net for "the customer
    loaded the page and never actually uploaded a KYC document," so a
    missed/never-fired OCR doesn't pin GPU memory indefinitely.
  - The OCR module calls mark_ocr_completed() the moment a real extraction
    finishes, which sleeps the model immediately, exactly matching "one OCR
    done, put model back to sleep" rather than waiting for the idle timeout.
"""
import os
import time
import logging
import threading
from datetime import datetime

import requests

from backend import kyc_ocr_warmth

logger = logging.getLogger("KYC_OCR_Warmup_Poller")

QR_PRINT_SERVER_BASE_URL = os.environ.get(
    "QR_PRINT_SERVER_BASE_URL", "https://print.aradhanajewellers.com"
)
WARMUP_SIGNAL_URL = f"{QR_PRINT_SERVER_BASE_URL}/api/kyc-ocr/warmup-signal"

POLL_INTERVAL_SECONDS = 1.5
SIGNAL_FRESHNESS_WINDOW_SECONDS = 180  # 3 minutes -- ignore stale page-load signals
IDLE_TIMEOUT_SECONDS = 240  # 4 minutes -- sleep anyway if no OCR ever claims the warm-up

warmup_poller_status = {
    "last_check": None,
    "last_signal_seconds_ago": None,
    "model_warmed_at": None,
    "last_error": None,
    "is_running": False,
}
_status_lock = threading.Lock()
_state_lock = threading.Lock()
_model_warmed_at = None  # datetime or None -- when we last successfully warmed it


def _update_status(**kwargs):
    with _status_lock:
        for key, value in kwargs.items():
            if key in warmup_poller_status:
                warmup_poller_status[key] = value


def mark_ocr_completed():
    """Call this the moment a real KYC-OCR extraction finishes. Sleeps the
    model immediately, regardless of the idle timeout."""
    global _model_warmed_at
    kyc_ocr_warmth.sleep()
    with _state_lock:
        _model_warmed_at = None
    _update_status(model_warmed_at=None)
    logger.info("OCR completed -- model put back to sleep.")


def _check_and_manage_warmth():
    global _model_warmed_at
    _update_status(is_running=True, last_check=datetime.now().isoformat())

    try:
        resp = requests.get(WARMUP_SIGNAL_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        seconds_ago = data.get("seconds_ago")
        _update_status(last_signal_seconds_ago=seconds_ago, last_error=None)

        with _state_lock:
            already_warm = _model_warmed_at is not None

        is_fresh = seconds_ago is not None and seconds_ago <= SIGNAL_FRESHNESS_WINDOW_SECONDS

        if is_fresh and not already_warm:
            if kyc_ocr_warmth.warm():
                with _state_lock:
                    _model_warmed_at = datetime.now()
                _update_status(model_warmed_at=_model_warmed_at.isoformat())
                logger.info(f"Warmed model (signal was {seconds_ago:.1f}s old).")
            else:
                # warm() timing out isn't a failure -- the load may still be
                # happening server-side. Record the attempt so the idle
                # timeout still applies rather than retrying every poll.
                with _state_lock:
                    _model_warmed_at = datetime.now()
                _update_status(model_warmed_at=_model_warmed_at.isoformat())

        with _state_lock:
            warmed_at = _model_warmed_at
        if warmed_at is not None:
            idle_seconds = (datetime.now() - warmed_at).total_seconds()
            if idle_seconds > IDLE_TIMEOUT_SECONDS:
                logger.info(
                    f"No OCR claimed the warm model within {IDLE_TIMEOUT_SECONDS}s -- "
                    "sleeping it (idle-timeout safety net)."
                )
                kyc_ocr_warmth.sleep()
                with _state_lock:
                    _model_warmed_at = None
                _update_status(model_warmed_at=None)

    except Exception as exc:
        _update_status(last_error=str(exc))
        logger.warning(f"Warm-up signal poll failed: {exc}")
    finally:
        _update_status(is_running=False)


def start_kyc_ocr_warmup_poller():
    def run():
        while True:
            _check_and_manage_warmth()
            time.sleep(POLL_INTERVAL_SECONDS)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info("KYC-OCR warm-up poller thread started.")
