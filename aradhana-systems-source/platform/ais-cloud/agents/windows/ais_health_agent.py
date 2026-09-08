"""Outbound-only AIS health agent. No remote command execution."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


PLATFORM_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = PLATFORM_ROOT / "core" / "ais.registry.json"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def local_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 80))
            return str(probe.getsockname()[0])
        except OSError:
            return "127.0.0.1"


def probe(url: str) -> str:
    try:
        with urlopen(Request(url, headers={"User-Agent": "AIS-Health-Agent/1"}), timeout=3) as response:
            return "healthy" if 200 <= response.status < 300 else "warning"
    except (URLError, OSError, ValueError):
        return "error"


def build_heartbeat(device_id: str) -> dict:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    capabilities: list[str] = []
    states: list[str] = []
    for service in registry["services"]:
        if service["host"] != device_id:
            continue
        state = probe(service["health"])
        capabilities.append(f"service:{service['id']}:{state}")
        states.append(state)
    status = "error" if "error" in states else "warning" if "warning" in states else "healthy"
    return {
        "device_id": device_id,
        "hostname": socket.gethostname(),
        "ip_address": local_ip(),
        "status": status,
        "capabilities": capabilities + ["agent:outbound-health-v1", f"observed:{utc_now()}"],
    }


def post(gateway_url: str, token: str, payload: dict) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        gateway_url.rstrip("/") + "/api/v1/agents/heartbeat",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "AIS-Health-Agent/1"},
    )
    with urlopen(request, timeout=10) as response:
        if response.status != 202:
            raise RuntimeError(f"Gateway returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Send an outbound AIS device health heartbeat.")
    parser.add_argument("--gateway-url", default=os.getenv("AIS_GATEWAY_URL", ""))
    parser.add_argument("--device-id", default=os.getenv("AIS_DEVICE_ID", "home-laptop"))
    parser.add_argument("--token", default=os.getenv("AIS_AGENT_TOKEN", ""))
    args = parser.parse_args()
    if not args.gateway_url or not args.token:
        print("AIS_GATEWAY_URL and AIS_AGENT_TOKEN are required.", file=sys.stderr)
        return 2
    payload = build_heartbeat(args.device_id)
    result = post(args.gateway_url, args.token, payload)
    print(json.dumps({"sent": True, "heartbeat": payload, "gateway": result}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
