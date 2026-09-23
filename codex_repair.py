"""Validated import path for Codex-assisted repairs of rejected deliveries.

Codex image generation runs outside the local Catalogue Tool.  This module
provides the local, auditable half of that workflow: validate a replacement,
publish it to the correct category, preserve any failed delivery, approve the
label, and let review_queue atomically route the raw master to processed/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

import image_spec
import review_queue


AUDIT_PATH = Path(review_queue.BASE) / "data" / "codex_repair_imports.jsonl"


def _category_folder(label: str, raw: str | os.PathLike[str]) -> str:
    finished = review_queue._find_all_finished_outputs(label)
    if finished:
        primary = max(finished, key=os.path.getmtime)
        return Path(primary).parent.name
    raw_folder = Path(raw).parent.name
    inferred = re.sub(r"[^A-Za-z0-9]+", "", raw_folder.title())
    if not inferred:
        raise ValueError(f"Cannot infer output category for {label}")
    return inferred


def _archive_path(label: str, category_folder: str) -> Path:
    archive_dir = Path(review_queue.REJECTED_DIR) / category_folder
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    candidate = archive_dir / f"{label}_failed_before_codex_{stamp}.jpg"
    counter = 2
    while candidate.exists():
        candidate = archive_dir / f"{label}_failed_before_codex_{stamp}_{counter}.jpg"
        counter += 1
    return candidate


def import_repair(label: str, candidate: str | os.PathLike[str], *, note: str) -> dict:
    label = label.strip()
    if not label or Path(label).name != label:
        raise ValueError("label must be a plain catalogue tag")
    state = review_queue._load_state()
    row = state.get(label) or {}
    if row.get("verdict") != review_queue.REJECTED:
        raise ValueError(f"{label} is not currently rejected")

    raw = review_queue._find_original(label)
    if not raw or not Path(raw).is_file():
        raise FileNotFoundError(f"Raw master not found for {label}")
    source = Path(candidate).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Repair candidate does not exist: {source}")

    category_folder = _category_folder(label, raw)
    output_dir = Path(review_queue.OUTPUT_DIR) / category_folder
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{label}.jpg"

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{label}.codex-repair.", suffix=".jpg", dir=output_dir
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    archive: Path | None = None
    try:
        result = image_spec.convert_delivery_image(
            source, temporary, strategy="pad", minimum_jpeg_quality=88
        )
        if destination.exists():
            archive = _archive_path(label, category_folder)
            shutil.move(destination, archive)
        os.replace(temporary, destination)
        try:
            saved = review_queue.set_verdict(
                label,
                review_queue.APPROVED,
                note=f"Codex imagegen repair - {note.strip()}",
            )
        except Exception:
            destination.unlink(missing_ok=True)
            if archive and archive.exists():
                shutil.move(archive, destination)
            raise
    finally:
        temporary.unlink(missing_ok=True)

    audit = {
        "label": label,
        "candidate": str(source),
        "raw_master": str(Path(raw).resolve()),
        "destination": str(destination.resolve()),
        "archived_failed_delivery": str(archive.resolve()) if archive else None,
        "previous_reason": row.get("reason"),
        "previous_note": row.get("note"),
        "repair_note": note.strip(),
        "file_bytes": result.file_bytes,
        "imported_at": time.time(),
    }
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit, ensure_ascii=False) + "\n")
    return {"review": saved, **audit}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import one Codex repair")
    parser.add_argument("label")
    parser.add_argument("candidate")
    parser.add_argument("--note", required=True)
    args = parser.parse_args()
    print(json.dumps(import_repair(args.label, args.candidate, note=args.note), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
