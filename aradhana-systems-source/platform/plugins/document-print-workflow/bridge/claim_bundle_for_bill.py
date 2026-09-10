"""Claim a cached QR bundle so it disappears from every biller queue."""
from __future__ import annotations

import argparse
import json
import os
from urllib.request import Request, urlopen


def claim(scanner_api: str, bundle_id: str, bridge_token: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if bridge_token:
        headers["X-Document-Bridge-Token"] = bridge_token
    request = Request(
        scanner_api.rstrip("/") + "/api/document-bundles/" + bundle_id + "/claim-for-bill",
        data=b"{}", method="POST", headers=headers,
    )
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scanner-api", required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--bridge-token", default=os.environ.get("AIS_DOCUMENT_BRIDGE_TOKEN", ""))
    args = parser.parse_args()
    print(json.dumps(claim(args.scanner_api, args.bundle_id, args.bridge_token), sort_keys=True))
