"""Queue one explicit held-document bundle through the QR Print Server."""
from __future__ import annotations

import argparse
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scanner-api", required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--token", default=os.environ.get("AIS_DOCUMENT_BRIDGE_TOKEN", ""))
    args = parser.parse_args()
    url = f"{args.scanner_api.rstrip('/')}/api/document-bundles/{quote(args.bundle_id, safe='')}/print-standalone"
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["X-Document-Bridge-Token"] = args.token
    request = Request(url, data=b"{}", method="POST", headers=headers)
    with urlopen(request, timeout=12) as response:
        print(json.dumps(json.loads(response.read().decode("utf-8")), sort_keys=True))


if __name__ == "__main__":
    main()
