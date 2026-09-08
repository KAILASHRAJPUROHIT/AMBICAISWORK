"""AIS Control Center: read-only, loopback-only platform inventory and health."""
from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "core" / "ais.registry.json"
DEVICES_PATH = ROOT / "core" / "ais.devices.json"
LOCAL_DEVICE_ID = os.environ.get("AIS_DEVICE_ID", "home-laptop")

app = Flask(__name__)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def is_loopback_request() -> bool:
    return request.remote_addr in {"127.0.0.1", "::1"}


def local_probe(url: str) -> tuple[str, str]:
    """Only probes endpoints explicitly declared in the local registry."""
    try:
        with urlopen(Request(url, headers={"User-Agent": "AIS-Control-Center/1"}), timeout=2) as response:
            return ("healthy" if 200 <= response.status < 300 else f"http_{response.status}", "")
    except (URLError, OSError, ValueError) as error:
        return "unreachable", str(error)[:180]


def status() -> dict:
    registry = load_json(REGISTRY_PATH)
    services = []
    for service in registry["services"]:
        item = dict(service)
        if service["id"] == "ais-control-center":
            item["state"], item["detail"] = "healthy", "Current process"
        elif service["host"] == LOCAL_DEVICE_ID:
            item["state"], item["detail"] = local_probe(service["health"])
        else:
            item["state"], item["detail"] = "remote_declared", "Probe from its owner device"
        services.append(item)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "device_id": LOCAL_DEVICE_ID,
        "hostname": socket.gethostname(),
        "services": services,
    }


@app.before_request
def require_loopback() -> None:
    if not is_loopback_request():
        return jsonify(error="AIS Control Center is loopback-only."), 403


@app.get("/health")
def health():
    return jsonify(status="healthy", component="ais-control-center", device_id=LOCAL_DEVICE_ID)


@app.get("/api/v1/registry")
def registry():
    # Registry and device inventory intentionally contain no credentials.
    return jsonify(registry=load_json(REGISTRY_PATH), devices=load_json(DEVICES_PATH))


@app.get("/api/v1/status")
def platform_status():
    return jsonify(status())


@app.get("/")
def index():
    return render_template("index.html", platform="AIS", organization="Aradhana Jewellers")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("AIS_CONTROL_CENTER_PORT", "8120")), debug=False)
