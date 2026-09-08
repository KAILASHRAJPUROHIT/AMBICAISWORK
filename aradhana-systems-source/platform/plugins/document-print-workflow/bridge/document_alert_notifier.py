"""Interactive LAN alert agent for newly queued QR document bundles.

Run one instance in each signed-in biller session. It never attaches documents
to a bill: attachment is available only from the Router's Alt+P decision view.
"""
from __future__ import annotations

import argparse
import json
import os
import tkinter as tk
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

NAVY, NAVY_DARK, GOLD, WHITE, MUTED, GREEN = "#173f7a", "#0e2d5a", "#f2c94c", "#ffffff", "#d9e5fa", "#4fc28a"


def request_json(url: str, method: str = "GET", token: str = "") -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Document-Bridge-Token"] = token
    request = Request(url, data=b"{}" if method == "POST" else None, method=method, headers=headers)
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def recent(bundle: dict) -> bool:
    try:
        created = datetime.fromisoformat(bundle["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created >= datetime.now(timezone.utc) - timedelta(minutes=30)
    except (KeyError, TypeError, ValueError):
        return False


class DocumentAlertNotifier:
    def __init__(self, root: tk.Tk, scanner_api: str, token: str, poll_seconds: int) -> None:
        self.root, self.scanner_api, self.token = root, scanner_api.rstrip("/"), token
        self.poll_ms = max(2, poll_seconds) * 1000
        self.known: set[str] = set()
        self.active: dict[str, tuple[tk.Toplevel, tk.Label]] = {}
        root.withdraw()
        self.poll(seed=True)

    def fetch(self) -> list[dict]:
        return request_json(self.scanner_api + "/api/document-bundles/pending", token=self.token).get("bundles", [])

    def poll(self, seed: bool = False) -> None:
        try:
            bundles = self.fetch()
            pending_ids = {bundle["bundle_id"] for bundle in bundles}
            for bundle_id, (window, _) in list(self.active.items()):
                if bundle_id not in pending_ids:
                    window.destroy()
                    self.active.pop(bundle_id, None)
            for bundle in bundles:
                bundle_id = bundle["bundle_id"]
                if not seed and bundle_id not in self.known and recent(bundle) and len(self.active) < 3:
                    self.show(bundle)
                elif bundle_id in self.active:
                    # OCR can refine a generic scan label after the initial
                    # toast appears. Update display-only metadata in place;
                    # never alter its held/print decision state.
                    self.active[bundle_id][1].config(text=bundle.get("display_name", "Pending ID documents"))
                self.known.add(bundle_id)
        except Exception:
            pass  # A transient network error must not kill the biller's alert agent.
        self.root.after(self.poll_ms, self.poll)

    def reposition(self) -> None:
        for index, (window, _) in enumerate(self.active.values()):
            width, height = 410, 150
            window.geometry(f"{width}x{height}+{self.root.winfo_screenwidth() - width - 22}+{58 + (index * (height + 10))}")

    def show(self, bundle: dict) -> None:
        bundle_id = bundle["bundle_id"]
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.90)
        window.configure(bg=NAVY)
        frame = tk.Frame(window, bg=NAVY, highlightbackground=GOLD, highlightthickness=1)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="NEW DOCUMENT READY", bg=NAVY_DARK, fg=GOLD,
                 font=("Segoe UI", 12, "bold")).pack(fill="x", padx=1, pady=(1, 8))
        name_label = tk.Label(frame, text=bundle.get("display_name", "Pending ID documents"), bg=NAVY, fg=WHITE,
                              anchor="w", wraplength=375, justify="left", font=("Segoe UI", 10, "bold"))
        name_label.pack(fill="x", padx=14)
        tk.Label(frame, text=f"{bundle_id}  •  Held until you choose Print documents", bg=NAVY, fg=MUTED,
                 anchor="w", font=("Segoe UI", 8)).pack(fill="x", padx=14, pady=(4, 9))
        actions = tk.Frame(frame, bg=NAVY)
        actions.pack(fill="x", padx=14, pady=(0, 10))
        tk.Button(actions, text="Print documents now", command=lambda: self.print_now(bundle), bg=GREEN, fg=WHITE,
                  relief="flat", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Button(actions, text="Dismiss", command=lambda: self.dismiss(bundle_id), bg=NAVY_DARK, fg=WHITE,
                  relief="flat", font=("Segoe UI", 9)).pack(side="right")
        self.active[bundle_id] = (window, name_label)
        self.reposition()

    def dismiss(self, bundle_id: str) -> None:
        active = self.active.pop(bundle_id, None)
        if active:
            active[0].destroy()
        self.reposition()

    def print_now(self, bundle: dict) -> None:
        bundle_id = bundle["bundle_id"]
        try:
            url = self.scanner_api + "/api/document-bundles/" + quote(bundle_id, safe="") + "/print-standalone"
            request_json(url, "POST", self.token)
            self.dismiss(bundle_id)
        except Exception:
            # Keep the toast visible: the documents are still held and retryable.
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scanner-api", required=True)
    parser.add_argument("--token", default=os.environ.get("AIS_DOCUMENT_BRIDGE_TOKEN", ""))
    parser.add_argument("--poll-seconds", type=int, default=5)
    args = parser.parse_args()
    if not args.token:
        raise SystemExit("AIS_DOCUMENT_BRIDGE_TOKEN is required")
    root = tk.Tk()
    DocumentAlertNotifier(root, args.scanner_api, args.token, args.poll_seconds)
    root.mainloop()


if __name__ == "__main__":
    main()
