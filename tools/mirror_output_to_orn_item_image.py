"""One-way, byte-for-byte output mirror for Ornate NX's image share.

Source is authoritative. Files created/changed below output are copied to the
same relative path below the Orn Item Image share. A source deletion removes
only the corresponding destination file that this mirror previously owned.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "output"
DESTINATION_ROOT = Path(r"\\Server2k22\D\Ornnx\Orn Images\Orn Item Image")
STATE_PATH = ROOT / "data" / "output_to_orn_item_image_mirror.json"
STATUS_PATH = ROOT / "data" / "output_to_orn_item_image_mirror_status.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
POLL_SECONDS = 1.0


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _load_state() -> dict:
    try:
        loaded = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {"files": {}}
    except FileNotFoundError:
        return {"files": {}}
    except Exception:
        # Never infer deletions from a corrupt ledger. Preserve remote data
        # until the next successful source scan rebuilds safe ownership.
        return {"files": {}}


def _image_files() -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in SOURCE_ROOT.rglob("*"):
        if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS:
            relative = path.relative_to(SOURCE_ROOT).as_posix()
            files[relative] = path
    return files


def _destination_for(relative: str) -> Path:
    candidate = (DESTINATION_ROOT / Path(relative)).resolve()
    destination_root = DESTINATION_ROOT.resolve()
    if candidate != destination_root and destination_root not in candidate.parents:
        raise ValueError(f"unsafe relative path: {relative!r}")
    return candidate


def _copy_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Same directory makes os.replace atomic on the SMB share.
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def sync_once() -> dict:
    started = time.time()
    if not SOURCE_ROOT.is_dir():
        raise RuntimeError(f"source unavailable: {SOURCE_ROOT}")
    if not DESTINATION_ROOT.is_dir():
        raise RuntimeError(f"destination unavailable: {DESTINATION_ROOT}")

    state = _load_state()
    previous = state.get("files") if isinstance(state.get("files"), dict) else {}
    current = _image_files()
    next_files: dict[str, dict] = {}
    copied = updated = deleted = 0
    errors: list[dict] = []

    for relative, source in current.items():
        try:
            stat = source.stat()
            fingerprint = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            destination = _destination_for(relative)
            old = previous.get(relative)
            needs_copy = old != fingerprint or not destination.is_file()
            if needs_copy:
                _copy_atomic(source, destination)
                if old is None:
                    copied += 1
                else:
                    updated += 1
            next_files[relative] = fingerprint
        except Exception as exc:
            # Keep the prior ownership record so a temporary SMB error can
            # never turn into a false deletion on the next poll.
            if relative in previous:
                next_files[relative] = previous[relative]
            errors.append({"path": relative, "error": f"{type(exc).__name__}: {exc}"})

    # Delete only paths already recorded in our own ledger. Never sweep or
    # remove unrelated Ornate NX files from the shared destination.
    for relative in set(previous) - set(current):
        try:
            destination = _destination_for(relative)
            if destination.is_file():
                destination.unlink()
                deleted += 1
            parent = destination.parent
            while parent != DESTINATION_ROOT and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        except Exception as exc:
            next_files[relative] = previous[relative]
            errors.append({"path": relative, "error": f"{type(exc).__name__}: {exc}"})

    _atomic_json(STATE_PATH, {"version": 1, "files": next_files, "updated_at": time.time()})
    result = {
        "ok": not errors,
        "started_at": started,
        "finished_at": time.time(),
        "source_images": len(current),
        "copied": copied,
        "updated": updated,
        "deleted": deleted,
        "errors": errors,
    }
    _atomic_json(STATUS_PATH, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    watch = args.watch or not args.once
    while True:
        try:
            result = sync_once()
            if result["copied"] or result["updated"] or result["deleted"] or result["errors"]:
                print(json.dumps(result), flush=True)
        except Exception as exc:
            result = {"ok": False, "finished_at": time.time(), "error": f"{type(exc).__name__}: {exc}"}
            try:
                _atomic_json(STATUS_PATH, result)
            except Exception:
                pass
            print(json.dumps(result), file=sys.stderr, flush=True)
        if not watch:
            return 0 if result.get("ok") else 1
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
