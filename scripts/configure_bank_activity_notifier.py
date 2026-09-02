"""Interactive per-PC setup for the native bank-activity notifier."""
import json
import os
import tkinter as tk
from tkinter import ttk

PATH = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "AradhanaBankActivityNotifier", "settings.json")
DEFAULTS = {"server_url": "http://127.0.0.1:8000/api/bank-activity", "poll_seconds": 1, "display_seconds": 30, "opacity": 92, "max_alerts": 3, "sound": False, "sound_threshold": 100000, "position": "centre-right"}
try:
    with open(PATH, encoding="utf-8") as source: values = {**DEFAULTS, **json.load(source)}
except (OSError, json.JSONDecodeError): values = DEFAULTS

root = tk.Tk(); root.title("Aradhana Bank Popup Setup"); root.resizable(False, False)
frame = ttk.Frame(root, padding=20); frame.grid()
fields = {}
for row, (label, key) in enumerate((("Bank Activity API URL", "server_url"), ("Poll every seconds", "poll_seconds"), ("Popup duration seconds", "display_seconds"), ("Transparency % (50-100)", "opacity"), ("Maximum stacked popups (1-5)", "max_alerts"), ("Sound above amount", "sound_threshold"))):
    ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
    entry = ttk.Entry(frame, width=44); entry.insert(0, str(values[key])); entry.grid(row=row, column=1, pady=5); fields[key] = entry
sound = tk.BooleanVar(value=bool(values["sound"])); ttk.Checkbutton(frame, text="Play sound for large transactions", variable=sound).grid(row=6, column=0, columnspan=2, sticky="w", pady=5)
ttk.Label(frame, text="Popup position").grid(row=7, column=0, sticky="w", pady=5)
position = ttk.Combobox(frame, values=("centre-right", "bottom-right"), state="readonly", width=20); position.set(values["position"]); position.grid(row=7, column=1, sticky="w", pady=5)
status = ttk.Label(frame, text="Changes apply when the notifier is next started."); status.grid(row=9, column=0, columnspan=2, sticky="w", pady=(12, 0))
def save():
    try:
        updated = {"server_url": fields["server_url"].get().strip(), "poll_seconds": max(1, int(fields["poll_seconds"].get())), "display_seconds": max(1, int(fields["display_seconds"].get())), "opacity": min(100, max(50, int(fields["opacity"].get()))), "max_alerts": min(5, max(1, int(fields["max_alerts"].get()))), "sound": sound.get(), "sound_threshold": max(0, float(fields["sound_threshold"].get())), "position": position.get()}
        if not updated["server_url"].startswith("http"): raise ValueError("Enter a valid http:// or https:// API URL")
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH, "w", encoding="utf-8") as target: json.dump(updated, target, indent=2)
        status.configure(text="Saved. Restart the notifier or sign out/in to apply.")
    except ValueError as error: status.configure(text=f"Invalid setting: {error}")
ttk.Button(frame, text="Save settings", command=save).grid(row=8, column=1, sticky="e", pady=12)
root.mainloop()
