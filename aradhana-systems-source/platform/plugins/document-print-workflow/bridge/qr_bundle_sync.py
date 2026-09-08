"""Copies pending QR Scanner metadata into AIS. Files are never downloaded here."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen


def request_json(url: str, method: str = "GET", body: dict | None = None, bridge_token: str = "") -> dict:
    encoded = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if bridge_token:
        headers["X-Document-Bridge-Token"] = bridge_token
    req = Request(url, data=encoded, method=method, headers=headers)
    with urlopen(req, timeout=8) as response:
        return json.loads(response.read().decode())


def sync(scanner_api: str, workflow_api: str, bridge_token: str = "") -> int:
    bundles = request_json(scanner_api.rstrip("/") + "/api/document-bundles/pending", bridge_token=bridge_token).get("bundles", [])
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    eligible = []
    for bundle in bundles:
        try:
            created = datetime.fromisoformat(str(bundle["created_at"]).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created >= cutoff:
                eligible.append(bundle)
        except (KeyError, TypeError, ValueError):
            continue
    # Cloud returns newest first. The biller sees at most three recent choices.
    eligible = eligible[:3]
    for bundle in eligible:
        request_json(workflow_api.rstrip("/") + "/api/v1/document-bundles", "POST", {
            "bundle_id": bundle["bundle_id"], "display_name": bundle["display_name"],
            "created_at": bundle.get("created_at"),
        })
    return len(eligible)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scanner-api", required=True)
    parser.add_argument("--workflow-api", default="http://127.0.0.1:8310")
    parser.add_argument("--bridge-token", default=os.environ.get("AIS_DOCUMENT_BRIDGE_TOKEN", ""))
    args = parser.parse_args()
    count = sync(args.scanner_api, args.workflow_api, args.bridge_token)
    print(json.dumps({"synced": count, "eligible": count}))
