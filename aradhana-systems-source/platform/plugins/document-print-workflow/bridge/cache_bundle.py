"""Downloads one biller-selected QR bundle into a local, checksummed renderer manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def download(url: str, bridge_token: str, timeout: int) -> bytes:
    headers = {"X-Document-Bridge-Token": bridge_token} if bridge_token else {}
    with urlopen(Request(url, headers=headers), timeout=timeout) as response:
        return response.read()


def cache_bundle(scanner_api: str, bundle_id: str, cache_root: Path, bridge_token: str = "") -> Path:
    bundle = json.loads(download(scanner_api.rstrip("/") + "/api/document-bundles/" + bundle_id, bridge_token, 10).decode())
    target = cache_root / bundle_id
    target.mkdir(parents=True, exist_ok=True)
    documents = []
    for item in bundle.get("files", []):
        name = Path(item["filename"]).name
        if not name or name != item["filename"]:
            raise ValueError("unsafe scanner filename")
        data = download(item["url"], bridge_token, 30)
        path = target / name
        path.write_bytes(data)
        documents.append({"local_path": str(path), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = target / "manifest.json"
    manifest.write_text(json.dumps({
        "bundle_id": bundle_id,
        "display_name": bundle["display_name"],
        # QR Scanner is the authority for this choice. Legacy bundles without
        # a mode use the safe full-page layout rather than image-shape guesses.
        "print_mode": bundle.get("print_mode") or "pdf",
        "documents": documents,
    }, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scanner-api", required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--cache-root", default=r"C:\PrintBridge\document_bundles")
    parser.add_argument("--bridge-token", default=os.environ.get("AIS_DOCUMENT_BRIDGE_TOKEN", ""))
    args = parser.parse_args()
    print(cache_bundle(args.scanner_api, args.bundle_id, Path(args.cache_root), args.bridge_token))
