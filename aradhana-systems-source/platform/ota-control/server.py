"""AIS OTA control plane. LAN-only signed release delivery."""
from __future__ import annotations

import json
import os
from ipaddress import ip_address
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

ROOT = Path(os.environ.get("AIS_OTA_ROOT", r"C:\AradhanaSystems\ota-releases"))
PUBLIC_CERTIFICATE = ROOT / "keys" / "ota-public.cer"
app = FastAPI(title="AIS OTA Control", docs_url=None, redoc_url=None)


def lan_client(request: Request) -> None:
    host = request.client.host if request.client else ""
    try:
        address = ip_address(host)
    except ValueError as exc:
        raise HTTPException(403, "Invalid client address") from exc
    if not (address.is_private or address.is_loopback):
        raise HTTPException(403, "LAN access only")


def release_dir(channel: str, target: str) -> Path:
    if channel not in {"beta", "stable"} or not target.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(404, "Release not found")
    return ROOT / "channels" / channel / target


@app.get("/health")
def health(request: Request):
    lan_client(request)
    return {"status": "healthy", "public_certificate": PUBLIC_CERTIFICATE.is_file()}


@app.get("/v1/public-certificate")
def public_certificate(request: Request):
    lan_client(request)
    if not PUBLIC_CERTIFICATE.is_file():
        raise HTTPException(503, "OTA signing certificate is not initialized")
    return FileResponse(PUBLIC_CERTIFICATE, media_type="application/pkix-cert", filename="ota-public.cer")


@app.get("/v1/releases/{channel}/{target}/current")
def current_release(channel: str, target: str, request: Request):
    lan_client(request)
    current = release_dir(channel, target) / "current.json"
    if not current.is_file():
        raise HTTPException(404, "No release published")
    return json.loads(current.read_text(encoding="utf-8"))


@app.get("/v1/releases/{channel}/{target}/artifacts/{version}/{filename}")
def artifact(channel: str, target: str, version: str, filename: str, request: Request):
    lan_client(request)
    if Path(filename).name != filename or Path(version).name != version:
        raise HTTPException(404, "Artifact not found")
    candidate = release_dir(channel, target) / "artifacts" / version / filename
    if not candidate.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(candidate, media_type="application/octet-stream", filename=filename)
