"""Atomic tombstones for capture pairs that must never be processed.

The capture tree is an immutable audit archive.  An operator Undo therefore
records a primary image as void instead of deleting either member of the raw
pair.  Pipeline intake reads this registry fail-closed: an unreadable registry
must stop intake rather than risk queueing an item whose status is unknown.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Mapping


BASE = Path(__file__).resolve().parent
VOID_REGISTRY_ENV = "AJ_CAPTURE_VOID_REGISTRY_PATH"
DEFAULT_VOID_REGISTRY_PATH = BASE / "data" / "capture_voids.json"
REGISTRY_VERSION = 1


class VoidRegistryError(RuntimeError):
    """The void registry cannot be trusted or safely updated."""


_lock = threading.RLock()


def configured_void_registry_path() -> Path:
    configured = os.environ.get(VOID_REGISTRY_ENV, "").strip()
    if not configured:
        return DEFAULT_VOID_REGISTRY_PATH
    expanded = Path(os.path.expandvars(os.path.expanduser(configured)))
    if not expanded.is_absolute():
        expanded = BASE / expanded
    return expanded.resolve()


def load_void_registry(
    registry_path: str | os.PathLike[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return validated tombstones keyed by POSIX-style primary path.

    A missing file means no capture has been voided yet.  Every other read or
    schema error raises: treating corruption as an empty registry could send a
    deliberately voided item into generation.
    """

    path = _registry_path(registry_path)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VoidRegistryError(f"Capture void registry is unreadable: {path}: {exc}") from exc

    if not isinstance(raw, dict) or raw.get("version") != REGISTRY_VERSION:
        raise VoidRegistryError(f"Unsupported capture void registry schema: {path}")
    voids = raw.get("voids")
    if not isinstance(voids, dict):
        raise VoidRegistryError(f"Capture void registry has invalid 'voids': {path}")

    validated: dict[str, dict[str, Any]] = {}
    for key, record in voids.items():
        if not isinstance(key, str) or not isinstance(record, dict):
            raise VoidRegistryError(f"Capture void registry has an invalid record: {path}")
        primary = _normalise_relative(key)
        if record.get("primary_path") != primary:
            raise VoidRegistryError(
                f"Capture void registry key/path mismatch for {key!r}: {path}"
            )
        tag_path = record.get("tag_path")
        if not isinstance(tag_path, str):
            raise VoidRegistryError(f"Capture void record lacks tag_path for {key!r}: {path}")
        _normalise_relative(tag_path)
        if not isinstance(record.get("voided_at"), (int, float)):
            raise VoidRegistryError(f"Capture void record lacks voided_at for {key!r}: {path}")
        validated[primary] = dict(record)
    return validated


def voided_primary_paths(
    registry_path: str | os.PathLike[str] | None = None,
) -> frozenset[Path]:
    return frozenset(Path(path) for path in load_void_registry(registry_path))


def is_voided(
    primary_path: str | os.PathLike[str],
    registry_path: str | os.PathLike[str] | None = None,
) -> bool:
    normalised = _normalise_relative(primary_path)
    return normalised in load_void_registry(registry_path)


def record_void(
    *,
    primary_path: str | os.PathLike[str],
    tag_path: str | os.PathLike[str],
    tag_code: str,
    category: str,
    folder: str,
    primary_size: int,
    tag_size: int,
    registry_path: str | os.PathLike[str] | None = None,
    voided_at: float | None = None,
) -> dict[str, Any]:
    """Atomically append one immutable capture tombstone."""

    path = _registry_path(registry_path)
    primary = _normalise_relative(primary_path)
    tag = _normalise_relative(tag_path)
    timestamp = time.time() if voided_at is None else float(voided_at)
    record = {
        "primary_path": primary,
        "tag_path": tag,
        "tag_code": str(tag_code),
        "category": str(category),
        "folder": str(folder),
        "reason": "operator_undo",
        "voided_at": timestamp,
        "primary_size": int(primary_size),
        "tag_size": int(tag_size),
    }

    with _lock:
        voids = load_void_registry(path)
        existing = voids.get(primary)
        if existing is not None:
            stable_fields = (
                "primary_path",
                "tag_path",
                "tag_code",
                "category",
                "folder",
                "reason",
                "primary_size",
                "tag_size",
            )
            if any(existing.get(field) != record.get(field) for field in stable_fields):
                raise VoidRegistryError(f"Capture path already has a different tombstone: {primary}")
            # Crash recovery: the registry replace may have succeeded just
            # before a dedup write failed.  A retry must reuse that tombstone
            # so Undo can finish clearing duplicate memory.
            return existing
        voids[primary] = record
        _atomic_write_registry(path, {"version": REGISTRY_VERSION, "voids": voids})
    return record


def _registry_path(path: str | os.PathLike[str] | None) -> Path:
    return configured_void_registry_path() if path is None else Path(path).resolve()


def _normalise_relative(path: str | os.PathLike[str]) -> str:
    candidate = Path(path)
    if (
        candidate.is_absolute()
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise VoidRegistryError(f"Unsafe capture-relative path: {path}")
    return Path(*candidate.parts).as_posix()


def _atomic_write_registry(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception as exc:
        raise VoidRegistryError(f"Could not atomically update capture void registry: {path}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
