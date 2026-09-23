"""Local catalogue history and duplicate detection. No external AI services."""

from __future__ import annotations

import datetime
import glob
import json
import os
import shutil
import threading
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "catalogue_db.json")
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")
OFFSITE_BACKUP_DIR = os.path.join(os.path.expanduser("~"), "OneDrive", "AradhanaCatalogueBackups")
KEEP_DAYS = 30
HASH_DIST_THRESHOLD = 12


def _load():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, encoding="utf-8") as source:
                return json.load(source)
        except Exception:
            pass
    return {"entries": []}


def _backup_snapshot(min_interval_secs=6 * 3600, keep=30):
    if not os.path.exists(DB_PATH):
        return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        existing = sorted(glob.glob(os.path.join(BACKUP_DIR, "catalogue_db_*.json")))
        if existing and time.time() - os.path.getmtime(existing[-1]) < min_interval_secs:
            return
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"catalogue_db_{stamp}.json"
        shutil.copy2(DB_PATH, os.path.join(BACKUP_DIR, name))
        for stale in existing[:-keep]:
            try:
                os.remove(stale)
            except OSError:
                pass
        try:
            if os.path.isdir(os.path.dirname(OFFSITE_BACKUP_DIR)):
                os.makedirs(OFFSITE_BACKUP_DIR, exist_ok=True)
                shutil.copy2(DB_PATH, os.path.join(OFFSITE_BACKUP_DIR, name))
        except Exception:
            pass
    except Exception:
        pass


def _save(database):
    _backup_snapshot()
    temporary = DB_PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8") as target:
        json.dump(database, target, indent=2)
    os.replace(temporary, DB_PATH)


def start_periodic_backup_thread():
    def worker():
        while True:
            time.sleep(3600)
            _backup_snapshot()
    threading.Thread(target=worker, daemon=True, name="catalogue-db-backup").start()


def _prune(database):
    cutoff = time.time() - KEEP_DAYS * 86400
    database["entries"] = [entry for entry in database.get("entries", []) if entry.get("ts", 0) >= cutoff]
    return database


def _phash(path):
    try:
        import imagehash
        from PIL import Image
        with Image.open(path) as image:
            return str(imagehash.phash(image.convert("RGB")))
    except Exception:
        return None


def _hash_dist(first, second):
    try:
        import imagehash
        return imagehash.hex_to_hash(first) - imagehash.hex_to_hash(second)
    except Exception:
        return 999


def _fmt_date(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime("%d %b %Y %H:%M")


def verify_jewellery_present(output_path: str, _attempt: int = 1) -> dict:
    """Local non-white-content sanity check for generated catalogue images."""
    try:
        from PIL import Image, ImageChops
        with Image.open(output_path) as source:
            image = source.convert("RGB")
            image.thumbnail((512, 512))
        white = Image.new("RGB", image.size, "white")
        bbox = ImageChops.difference(image, white).getbbox()
        return {"ok": bbox is not None, "reason": "Local pixel-content check", "unverified": False}
    except Exception as exc:
        return {"ok": True, "reason": f"Local check unavailable: {exc}", "unverified": True}


def check_and_record(label: str, output_path: str, category: str = "") -> list:
    return _check(label, output_path, category, record=True)


def check_only(label: str, output_path: str, category: str = "") -> list:
    return _check(label, output_path, category, record=False)


def _check(label: str, output_path: str, category: str, record: bool) -> list:
    database = _prune(_load())
    clean_label = (label or "").strip().upper()
    new_hash = _phash(output_path) if output_path and os.path.exists(output_path) else None
    findings = []
    for entry in database["entries"]:
        old_label = (entry.get("label") or "").strip().upper()
        old_hash = entry.get("phash")
        distance = _hash_dist(new_hash, old_hash) if new_hash and old_hash else 999
        same_design = distance <= HASH_DIST_THRESHOLD
        if same_design and old_label == clean_label:
            kind = "exact_duplicate"
            message = f"Already processed as {old_label} on {_fmt_date(entry.get('ts', 0))}"
        elif same_design and old_label != clean_label:
            kind = "same_design_diff_tag"
            message = f"Visually similar to {old_label}; perceptual-hash distance {distance}"
        elif old_label == clean_label and not same_design:
            kind = "same_tag_diff_design"
            message = f"Tag {clean_label} exists with a different image"
        else:
            continue
        findings.append({
            "type": kind,
            "label": entry.get("label", ""),
            "date": _fmt_date(entry.get("ts", 0)),
            "output": entry.get("output", ""),
            "message": message,
        })
    if record:
        database["entries"].append({
            "label": label,
            "category": category,
            "output": output_path,
            "phash": new_hash,
            "ts": time.time(),
        })
        _save(database)
    return findings
