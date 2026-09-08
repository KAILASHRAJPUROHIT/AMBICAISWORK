"""Non-blocking top-right document decision toast for the Ornate Router."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
import tkinter as tk
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

NAVY, NAVY_DARK, GOLD, WHITE, MUTED, SUCCESS = "#173f7a", "#0e2d5a", "#f2c94c", "#ffffff", "#d9e5fa", "#4fc28a"


def api_json(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=4) as response:
        return json.loads(response.read().decode("utf-8"))


class BillerToast:
    """Never auto-attaches. Unattended expiry explicitly retains normal printing."""
    def __init__(self, root: tk.Tk, api_base: str, decision_file: Path, customer_name: str,
                 bill_reference: str) -> None:
        self.root, self.api_base, self.decision_file = root, api_base.rstrip("/"), decision_file
        self.finished, self.bundles = False, []
        session = api_json(f"{self.api_base}/api/v1/print-sessions", "POST", {
            "customer_name": customer_name, "bill_reference": bill_reference})
        self.session_id = session["id"]

        root.title("Aradhana Documents")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.90)
        root.configure(bg=NAVY)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.dismiss)
        frame = tk.Frame(root, bg=NAVY, highlightbackground=GOLD, highlightthickness=1)
        frame.pack(fill="both", expand=True)
        heading = tk.Frame(frame, bg=NAVY_DARK)
        heading.pack(fill="x")
        tk.Label(heading, text="DOCUMENTS READY", bg=NAVY_DARK, fg=GOLD,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=15, pady=10)
        tk.Label(heading, text="Choose before Print/OK", bg=NAVY_DARK, fg=WHITE,
                 font=("Segoe UI", 9, "bold")).pack(side="right", padx=13)
        self.summary = tk.Label(frame, text="Checking scanned documents…", bg=NAVY, fg=MUTED,
                                justify="left", anchor="w", wraplength=385, font=("Segoe UI", 9))
        self.summary.pack(fill="x", padx=15, pady=(11, 6))
        self.bundle_list = tk.Listbox(frame, height=3, exportselection=False, activestyle="none",
                                      bg=WHITE, fg="#16233a", selectbackground="#d5a91b",
                                      selectforeground="#16233a", font=("Segoe UI", 9), borderwidth=0)
        self.bundle_list.pack(fill="x", padx=15, pady=(0, 9))
        actions = tk.Frame(frame, bg=NAVY)
        actions.pack(fill="x", padx=15, pady=(0, 8))
        tk.Button(actions, text="Attach document", command=self.attach, bg=GOLD, fg="#17243a",
                  activebackground="#ffe289", font=("Segoe UI", 9, "bold"), relief="flat", padx=9).pack(side="left")
        tk.Button(actions, text="Print documents", command=self.standalone, bg=SUCCESS, fg=WHITE,
                  activebackground="#68d99e", font=("Segoe UI", 9, "bold"), relief="flat", padx=9).pack(side="left", padx=7)
        tk.Button(actions, text="Dismiss", command=self.dismiss, bg=NAVY_DARK, fg=WHITE,
                  activebackground="#244e8d", font=("Segoe UI", 9), relief="flat", padx=8).pack(side="right")
        self.notice = tk.Label(frame, text="", bg=NAVY, fg="#ffdf87", anchor="w", font=("Segoe UI", 8))
        self.notice.pack(fill="x", padx=15, pady=(0, 9))
        root.update_idletasks()
        width, height = 430, 250
        root.geometry(f"{width}x{height}+{root.winfo_screenwidth() - width - 22}+58")
        # Deliberately no focus request: Ornate stays usable beneath this toast.
        root.after(100, self.refresh)

    def selected_bundle_id(self) -> str | None:
        selected = self.bundle_list.curselection()
        return self.bundles[selected[0]]["id"] if selected and selected[0] < len(self.bundles) else None

    def refresh(self) -> None:
        if self.finished:
            return
        try:
            selected_id = self.selected_bundle_id()
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
            fetched = api_json(f"{self.api_base}/api/v1/document-bundles").get("bundles", [])
            self.bundles = []
            for bundle in fetched:
                try:
                    created = datetime.fromisoformat(bundle["created_at"].replace("Z", "+00:00"))
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if created >= cutoff:
                        self.bundles.append(bundle)
                except (KeyError, TypeError, ValueError):
                    continue
                if len(self.bundles) == 3:
                    break
            self.bundle_list.delete(0, tk.END)
            for bundle in self.bundles:
                self.bundle_list.insert(tk.END, f"{bundle['display_name']}  [{bundle['id']}]")
            if selected_id:
                for index, bundle in enumerate(self.bundles):
                    if bundle["id"] == selected_id:
                        self.bundle_list.selection_set(index)
                        break
            if self.bundles:
                names = " • ".join(bundle["display_name"] for bundle in self.bundles)
                self.summary.config(text=(f"Customer / OCR name: {names}\n"
                                          "Select only documents confirmed for this bill. Nothing attaches automatically."))
            else:
                self.summary.config(text="No pending documents. Bill will continue normally.")
        except (URLError, ValueError, KeyError) as error:
            self.summary.config(text="Document service unavailable. Bill will continue normally.")
            self.notice.config(text=str(error))
        self.root.after(1000, self.refresh)

    def decide(self, decision: str, bundle_id: str | None = None) -> None:
        if self.finished:
            return
        try:
            result = api_json(f"{self.api_base}/api/v1/print-sessions/{self.session_id}/decision", "POST", {
                "decision": decision, "bundle_id": bundle_id})
            self.decision_file.parent.mkdir(parents=True, exist_ok=True)
            self.decision_file.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
            self.finished = True
            self.root.destroy()
        except (URLError, ValueError, KeyError) as error:
            self.notice.config(text=f"Could not save choice: {error}. Please retry or close for normal print.")

    def require_bundle(self) -> str | None:
        bundle_id = self.selected_bundle_id()
        if not bundle_id:
            self.notice.config(text="Select one confirmed document bundle first.")
        return bundle_id

    def attach(self) -> None:
        bundle_id = self.require_bundle()
        if bundle_id:
            self.decide("attach", bundle_id)

    def standalone(self) -> None:
        """Queue the held documents only; never submits or changes the bill."""
        bundle_id = self.require_bundle()
        if bundle_id:
            self.decide("standalone", bundle_id)

    def dismiss(self) -> None:
        """Close the panel only; printing remains an explicit Ornate action."""
        self.decide("bill_only")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8310")
    parser.add_argument("--decision-file", required=True)
    parser.add_argument("--customer-name", default="")
    parser.add_argument("--bill-reference", default="")
    args = parser.parse_args()
    root = tk.Tk()
    BillerToast(root, args.api, Path(args.decision_file), args.customer_name,
                args.bill_reference)
    root.mainloop()


if __name__ == "__main__":
    main()
