"""
ai_advisor_server.py -- standalone local-AI advisory proxy, fully isolated
from both app.py and capture_server.py.

WHY A THIRD PROCESS: capture_server.py's own docstring is explicit that it
must have ZERO dependency on anything AI/engine-related, specifically
because a slow/hung engine call previously degraded or crashed the shared
Flask process capture depended on. Bolting a local-Ollama call directly onto
capture_server.py would reintroduce exactly that risk, just with Qwen
instead of Copilot/Gemini/Codex. This is the same isolation principle,
applied consistently: capture_server.py talks to capture_tool.py and
nothing else; this process talks to Ollama and nothing else. A hang or
crash here can never reach or block a real capture.

Ollama itself only binds 127.0.0.1 (confirmed 2026-08-28) -- unreachable
from the tablet directly. This proxy is the ONLY thing on this LAN that
needs to reach Ollama; it runs on the same laptop as capture_server.py, on
its own port, and forwards a small set of advisory questions to the local
qwen3-vl model already loaded (see project memory: "local Qwen almost
always loaded"). Every response is advisory only -- CaptureCam's Android
client must always fail open (treat "unreachable" or "unsure" the same as
"no opinion", never as a hard block or a hard pass) since this is a
convenience layer over geometry-based gates that already work standalone,
not a replacement for them. Firsthand measured limitation (see project
memory "Local AI can't verify jewellery design"): qwen3-vl reliably answers
coarse questions ("does this look roughly like X") but is NOT trustworthy
for fine design-match verification -- every endpoint here is scoped to
coarse questions only, on purpose.
"""
import base64
import json
import logging
import time
import urllib.request
import urllib.error

from flask import Flask, request, jsonify

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
# 4B, not 8B: capture is latency-sensitive and this is advisory-only --
# a slower, more accurate model isn't worth blocking the operator's flow.
MODEL = "qwen3-vl:4b-instruct-q4_K_M"
# Bounded so a stalled/overloaded Ollama can never hang a caller
# indefinitely -- callers must treat a timeout as "no opinion", not retry
# in a loop.
OLLAMA_TIMEOUT_S = 12

app = Flask(__name__)
log = logging.getLogger("ai_advisor")
logging.basicConfig(level=logging.INFO)


def _ask_ollama(prompt: str, image_b64: str) -> str | None:
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0.0},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return (body.get("response") or "").strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        log.warning("Ollama call failed: %s", e)
        return None


@app.route("/api/advise/shape", methods=["POST"])
def advise_shape():
    """Coarse yes/no: does the photographed object roughly look like the
    named jewellery category? Used as a fallback ONLY when CaptureCam's own
    geometry-based shape/edge-clip gate has already rejected a frame
    repeatedly -- never as the first-line check, and never for fine design
    verification (measured unreliable for that, see module docstring)."""
    started = time.time()
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image_b64")
    category_label = data.get("category_label")
    if not image_b64 or not category_label:
        return jsonify({"ok": False, "error": "image_b64 and category_label required"}), 400
    # Kept SHORT deliberately: the image itself already consumes ~4048 of
    # this model's 4096-token loaded context (confirmed 2026-08-28, a
    # verbose prompt alone pushed a real call over the limit with a
    # exceed_context_size_error) -- every word here is context budget the
    # image doesn't get.
    prompt = (
        f"Gold jewellery photo, framing may be imperfect. Could this be a "
        f"{category_label}? Answer only YES or NO."
    )
    answer = _ask_ollama(prompt, image_b64)
    elapsed_ms = int((time.time() - started) * 1000)
    if answer is None:
        return jsonify({"ok": False, "error": "model unreachable or timed out", "elapsedMs": elapsed_ms})
    normalized = answer.strip().upper()
    matches = normalized.startswith("YES") if normalized.startswith(("YES", "NO")) else None
    log.info(
        "advise_shape category=%s answer=%r matches=%s elapsedMs=%d",
        category_label, answer, matches, elapsed_ms,
    )
    return jsonify({"ok": True, "matches": matches, "raw": answer, "elapsedMs": elapsed_ms})


@app.route("/api/advise/health")
def health():
    """Deliberately does NOT call Ollama -- this only confirms the proxy
    process itself is up, so a caller can distinguish 'proxy down' from
    'proxy up but Ollama slow' without paying an inference cost just to
    check reachability."""
    return jsonify({"ok": True, "ts": time.time()})


if __name__ == "__main__":
    # Plain HTTP, LAN-only, non-sensitive advisory data (a coarse yes/no
    # about jewellery shape) -- no TLS complexity needed for this one,
    # unlike capture_server.py which also carries real capture/save
    # traffic. Runs in the foreground for now; add to supervisor.ps1 once
    # the Android-side integration is confirmed live.
    app.run(host="0.0.0.0", port=7661, threaded=True)
