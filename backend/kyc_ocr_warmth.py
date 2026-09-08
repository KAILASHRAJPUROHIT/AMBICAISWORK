"""Explicit warm/sleep control for the local KYC-OCR vision model.

The model stays unloaded (0 VRAM) by default. Something must call warm()
before an OCR call is expected, and sleep() once it's done -- Ollama's
keep_alive parameter is the actual mechanism; this module just wraps it
with the specific policy this system wants (see kyc_ocr_poller.py for the
warm-up trigger logic and the idle-timeout safety net).
"""
import logging
import requests

logger = logging.getLogger("KYC_OCR_Warmth")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3-vl:4b-instruct-q4_K_M"


def warm(timeout: float = 10.0) -> bool:
    """Force the model into VRAM without running real inference.

    A generate call with an empty prompt and keep_alive set still loads the
    model (that's the expensive part) but does essentially no generation
    work. Returns True if the model is loaded and ready, False on any
    failure (caller should treat False as "still cold, OCR call will pay
    the load cost itself").
    """
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": "", "keep_alive": "10m", "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        logger.info(f"Warm-up requested for {MODEL}")
        return True
    except requests.exceptions.Timeout:
        # A cold load can legitimately take longer than a short warm() timeout.
        # That's fine -- the load is still happening in the background on the
        # Ollama server side; we just don't wait around for it here.
        logger.info(f"Warm-up call for {MODEL} still loading (timed out waiting, not an error)")
        return False
    except Exception as exc:
        logger.warning(f"Warm-up call for {MODEL} failed: {exc}")
        return False


def sleep(timeout: float = 5.0) -> bool:
    """Explicitly unload the model from VRAM immediately (keep_alive=0)."""
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": "", "keep_alive": 0, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        logger.info(f"{MODEL} unloaded from VRAM")
        return True
    except Exception as exc:
        logger.warning(f"Failed to unload {MODEL}: {exc}")
        return False


def is_loaded(timeout: float = 5.0) -> bool:
    """Check whether the model currently occupies VRAM, via Ollama's /api/ps."""
    try:
        resp = requests.get("http://localhost:11434/api/ps", timeout=timeout)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        return any(m.get("name", "").startswith(MODEL.split(":")[0]) for m in models)
    except Exception as exc:
        logger.warning(f"Failed to check model load state: {exc}")
        return False
