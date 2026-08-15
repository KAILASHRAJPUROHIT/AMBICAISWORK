"""Publish approved catalogue images into Ornnx's stock image library."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PIL import Image

import ornament_code_map as ocm
import stock_excel

SERVER_ROOT = Path(os.environ.get(
    "ORNNX_ITEM_IMAGE_ROOT",
    r"\\Server2k22\D\Ornnx\Orn Images\Orn Item Image",
))
MANIFEST = Path(__file__).resolve().parent / "data" / "orn_item_uploads.json"
QUEUE = Path(__file__).resolve().parent / "data" / "orn_item_upload_queue.json"
STATUS = Path(__file__).resolve().parent / "data" / "orn_item_upload_status.json"
_lock = threading.Lock()


def _stock_labels(stock_labels=None) -> tuple[str, ...]:
    if stock_labels is not None:
        return tuple(str(value).strip() for value in stock_labels if str(value).strip())
    inventory = stock_excel.load_stock_label_inventory(stock_excel.latest_stock_workbook())
    return inventory.labels


def resolve_stock_identity(label: str, stock_labels=None) -> tuple[str, ocm.Category]:
    wanted = label.strip().casefold()
    matches = [
        stock_label for stock_label in _stock_labels(stock_labels)
        if stock_excel.safe_filename_label(stock_label).casefold() == wanted
    ]
    if len(matches) != 1:
        raise ValueError(f"{label}: expected one current-stock label, found {len(matches)}")
    stock_label = matches[0]
    category = ocm.category_from_tag_code(stock_label)
    if category is None:
        raise ValueError(f"{label}: stock category is unknown")
    return stock_label, category


def destination_for(label: str, *, server_root=SERVER_ROOT, stock_labels=None) -> Path:
    stock_label, category = resolve_stock_identity(label, stock_labels)
    # Windows cannot contain the workbook slash. Ornate NX's exact convention:
    # BL/100 in Excel -> BL_100.Jpg on disk.
    stem = stock_excel.safe_filename_label(stock_label)
    return Path(server_root) / category.label / f"{stem}.Jpg"


def create_stock_category_folders(*, server_root=SERVER_ROOT, stock_labels=None) -> dict:
    labels = _stock_labels(stock_labels)
    categories = {
        category.label
        for label in labels
        if (category := ocm.category_from_tag_code(label)) is not None
    }
    root = Path(server_root)
    root.mkdir(parents=True, exist_ok=True)
    created, existing = [], []
    for category_label in sorted(categories):
        folder = root / category_label
        if folder.is_dir():
            existing.append(category_label)
        else:
            folder.mkdir(parents=False, exist_ok=False)
            created.append(category_label)
    return {"root": str(root), "categories": len(categories), "created": created, "existing": existing}


def _save_manifest_row(label: str, row: dict, manifest_path: Path = MANIFEST) -> None:
    with _lock:
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        data[label] = row
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temporary, manifest_path)


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def uploaded_labels(manifest_path: Path = MANIFEST) -> tuple[str, ...]:
    return tuple(
        label for label, row in _load_json(Path(manifest_path)).items()
        if isinstance(row, dict) and row.get("ok") is True
    )


def queue_upload(label: str, source_path: str | os.PathLike[str], error=None,
                 *, queue_path: Path = QUEUE) -> dict:
    row = {
        "label": label,
        "source": str(source_path),
        "queued_at": time.time(),
    }
    if error is not None:
        row["last_error"] = f"{type(error).__name__}: {error}"
    with _lock:
        data = _load_json(Path(queue_path))
        data[label] = row
        Path(queue_path).parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(queue_path).with_suffix(Path(queue_path).suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temporary, queue_path)
    return {"ok": False, "queued": True, **row}


def _remove_queued(label: str, queue_path: Path = QUEUE) -> None:
    with _lock:
        data = _load_json(Path(queue_path))
        if label not in data:
            return
        data.pop(label, None)
        temporary = Path(queue_path).with_suffix(Path(queue_path).suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temporary, queue_path)


def trigger_user_upload_worker() -> None:
    """Run the user-context supervisor without blocking the approval request."""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        ["schtasks.exe", "/Run", "/TN", "AradhanaOrnItemUpload"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def publish_approved(label: str, source_path: str | os.PathLike[str], *,
                     server_root=SERVER_ROOT, stock_labels=None,
                     manifest_path: Path = MANIFEST,
                     queue_path: Path = QUEUE) -> dict:
    """Atomically publish one approved delivery as Ornate NX-compatible JPEG."""
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = destination_for(label, server_root=server_root, stock_labels=stock_labels)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        # Some SMB servers report ERROR_ALREADY_EXISTS even with exist_ok.
        pass
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with Image.open(source) as opened:
            opened.convert("RGB").save(
                temporary,
                format="JPEG",
                quality=95,
                subsampling=0,
                optimize=True,
            )
        with Image.open(temporary) as check:
            check.verify()
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    result = {"ok": True, "label": label, "source": str(source), "destination": str(destination), "uploaded_at": time.time()}
    _save_manifest_row(label, result, Path(manifest_path))
    _remove_queued(label, Path(queue_path))
    return result


def record_failure(label: str, error: Exception, *, manifest_path: Path = MANIFEST) -> dict:
    result = {"ok": False, "label": label, "error": f"{type(error).__name__}: {error}", "attempted_at": time.time()}
    _save_manifest_row(label, result, Path(manifest_path))
    return result


def drain_upload_queue(*, queue_path: Path = QUEUE, status_path: Path = STATUS) -> dict:
    queued = _load_json(Path(queue_path))
    published, failed = [], []
    for label, row in sorted(queued.items()):
        source = str((row or {}).get("source") or "")
        try:
            publish_approved(label, source, queue_path=Path(queue_path))
            published.append(label)
        except Exception as exc:
            record_failure(label, exc)
            queue_upload(label, source, exc, queue_path=Path(queue_path))
            failed.append({"label": label, "error": f"{type(exc).__name__}: {exc}"})
    result = {
        "ran_at": time.time(),
        "published": published,
        "failed": failed,
        "remaining": len(_load_json(Path(queue_path))),
    }
    Path(status_path).parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(status_path).with_suffix(Path(status_path).suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    os.replace(temporary, status_path)
    return result


if __name__ == "__main__" and "--drain-queue" in sys.argv:
    print(json.dumps(drain_upload_queue(), indent=2))
