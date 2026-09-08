"""Branded per-PC control centre for the native bank-activity notifier."""
import json
import os
import subprocess
import tkinter as tk
from datetime import datetime, timedelta, timezone
from tkinter import messagebox, ttk

NAVY, GOLD, LIGHT_GOLD = "#23519D", "#CCA137", "#F7CA5B"
APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "AradhanaBankActivityNotifier")
PATH = os.path.join(APP_DIR, "settings.json")
LOGO = r"C:\Content\Logos\Logo Dimensions in Reel 30% x=220 y=200.png"
if not os.path.exists(LOGO): LOGO = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
DEFAULTS = {"server_url": "http://ARADHANA:8000/api/bank-activity", "poll_seconds": 1, "display_seconds": 30, "opacity": 92, "max_alerts": 3, "sound": False, "sound_threshold": 100000, "position": "centre-right", "enabled": True, "paused_until": None, "popup_width": 360, "popup_height": 188}
try:
    with open(PATH, encoding="utf-8") as source: values = {**DEFAULTS, **json.load(source)}
except (OSError, json.JSONDecodeError): values = DEFAULTS

root = tk.Tk(); root.title("Aradhana Bank Activity Control"); root.configure(bg=NAVY); root.resizable(False, False)
shell = tk.Frame(root, bg=NAVY, padx=20, pady=18); shell.pack(fill="both", expand=True)
header = tk.Frame(shell, bg=NAVY); header.pack(fill="x")
if os.path.exists(LOGO):
    try:
        logo = tk.PhotoImage(file=LOGO); logo = logo.subsample(max(1, logo.width() // 80), max(1, logo.height() // 72)); tk.Label(header, image=logo, bg=NAVY).pack(side="left", padx=(0, 12)); root.logo = logo
    except tk.TclError: pass
tk.Label(header, text="BANK ACTIVITY\nNOTIFICATION CONTROL", bg=NAVY, fg=LIGHT_GOLD, justify="left", font=("Segoe UI", 15, "bold")).pack(side="left")
card = tk.Frame(shell, bg="white", padx=18, pady=14, highlightbackground=GOLD, highlightthickness=2); card.pack(fill="both", pady=(16, 0))
fields = {}
labels = (("Bank Activity API URL", "server_url"), ("Poll every seconds", "poll_seconds"), ("Popup duration seconds", "display_seconds"), ("Transparency % (50-100)", "opacity"), ("Maximum stacked popups (1-5)", "max_alerts"), ("Popup width px (minimum 360)", "popup_width"), ("Popup height px (minimum 188)", "popup_height"), ("Sound above amount", "sound_threshold"))
for row, (label, key) in enumerate(labels):
    tk.Label(card, text=label, bg="white", fg=NAVY, font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
    entry = ttk.Entry(card, width=40); entry.insert(0, str(values[key])); entry.grid(row=row, column=1, pady=4); fields[key] = entry
sound = tk.BooleanVar(value=bool(values["sound"])); enabled = tk.BooleanVar(value=bool(values["enabled"]))
ttk.Checkbutton(card, text="Play sound for large transactions", variable=sound).grid(row=8, column=0, columnspan=2, sticky="w", pady=4)
ttk.Checkbutton(card, text="Enable all bank popups", variable=enabled).grid(row=9, column=0, columnspan=2, sticky="w", pady=4)
tk.Label(card, text="Popup position", bg="white", fg=NAVY, font=("Segoe UI", 9, "bold")).grid(row=10, column=0, sticky="w", pady=4)
position = ttk.Combobox(card, values=("centre-right", "bottom-right"), state="readonly", width=20); position.set(values["position"]); position.grid(row=10, column=1, sticky="w")
tk.Label(card, text="Pause popups", bg="white", fg=NAVY, font=("Segoe UI", 9, "bold")).grid(row=11, column=0, sticky="w", pady=4)
pause_value = ttk.Entry(card, width=8); pause_value.insert(0, "0"); pause_value.grid(row=11, column=1, sticky="w")
pause_unit = ttk.Combobox(card, values=("minutes", "hours", "days"), state="readonly", width=12); pause_unit.set("minutes"); pause_unit.grid(row=11, column=1, sticky="e")
status = tk.Label(card, text="Minimum size is safety-gated so amount, bank, and Ref/UTR always fit.", bg="white", fg="#4b5563", wraplength=470, justify="left"); status.grid(row=13, column=0, columnspan=2, sticky="w", pady=(12, 0))
def save():
    try:
        seconds = {"minutes": 60, "hours": 3600, "days": 86400}[pause_unit.get()] * max(0, int(pause_value.get()))
        updated = {"server_url": fields["server_url"].get().strip(), "poll_seconds": max(1, int(fields["poll_seconds"].get())), "display_seconds": max(1, int(fields["display_seconds"].get())), "opacity": min(100, max(50, int(fields["opacity"].get()))), "max_alerts": min(5, max(1, int(fields["max_alerts"].get()))), "popup_width": max(360, int(fields["popup_width"].get())), "popup_height": max(188, int(fields["popup_height"].get())), "sound": sound.get(), "sound_threshold": max(0, float(fields["sound_threshold"].get())), "position": position.get(), "enabled": enabled.get(), "paused_until": (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat() if seconds else None}
        if not updated["server_url"].startswith("http"): raise ValueError("Enter a valid http:// or https:// API URL")
        os.makedirs(APP_DIR, exist_ok=True)
        with open(PATH, "w", encoding="utf-8") as target: json.dump(updated, target, indent=2)
        status.configure(text="Saved. Pause/disable survives reboot. Restart notifier or sign out/in to apply live settings.", fg="#047857")
    except ValueError as error: status.configure(text=f"Invalid setting: {error}", fg="#b91c1c")
def cleanup():
    if not messagebox.askyesno("Remove notifier", "Remove all notifier tasks, settings, firewall rules, and active popup processes from this PC?"): return
    script = os.path.join(os.path.dirname(__file__), "remove_bank_activity_notifier.ps1")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{script}\"'"])
    root.destroy()
buttons = tk.Frame(card, bg="white"); buttons.grid(row=12, column=0, columnspan=2, sticky="ew", pady=12)
ttk.Button(buttons, text="Save settings", command=save).pack(side="left")
ttk.Button(buttons, text="Remove from this PC", command=cleanup).pack(side="right")
root.mainloop()
