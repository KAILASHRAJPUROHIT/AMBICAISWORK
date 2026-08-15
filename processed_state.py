"""Processed-item lifecycle and recoverable reset controls.

Success is represented by BOTH the source image living under ``processed/``
and its tag being present in the progress/duplicate-memory stores.  Resetting
reverses only that state: sources move back to ``processing/`` and memory
records are removed.  Master capture and generated outputs are never touched.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import ornament_code_map
import paths


_LOCK = threading.RLock()
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
_TOKEN_SPLIT = re.compile(r"[\s,;]+")
_RANGE = re.compile(
    r"^([A-Z]+\d*)[_/-](\d+)-(?:([A-Z]+\d*)[_/-])?(\d+)$",
    re.IGNORECASE,
)


def normalize_tag(value: str) -> str:
    return re.sub(r"[/\\-]+", "_", (value or "").strip().upper())


def parse_tag_series(value: str, *, maximum: int = 5000) -> tuple[str, ...]:
    """Parse tags separated by spaces/lines/commas plus compact ranges.

    Examples: ``LR22_7, LR22_10`` and ``LR22_40-LR22_69``.
    """
    tags: list[str] = []
    seen: set[str] = set()
    for token in filter(None, _TOKEN_SPLIT.split(value or "")):
        match = _RANGE.match(token)
        if match:
            prefix_a, start, prefix_b, end = match.groups()
            prefix_a = prefix_a.upper()
            prefix_b = (prefix_b or prefix_a).upper()
            if prefix_a != prefix_b:
                raise ValueError(f"Range prefixes differ: {token}")
            first, last = int(start), int(end)
            if last < first:
                raise ValueError(f"Range runs backwards: {token}")
            expanded = (f"{prefix_a}_{number}" for number in range(first, last + 1))
        else:
            normalized = normalize_tag(token)
            if not re.fullmatch(r"[A-Z0-9]+_\d+", normalized):
                raise ValueError(f"Invalid tag: {token}")
            expanded = (normalized,)
        for tag in expanded:
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
                if len(tags) > maximum:
                    raise ValueError(f"Too many tags; maximum is {maximum}")
    return tuple(tags)


def _tag_for_file(path: Path) -> str:
    stem = path.stem[:-2] if path.stem.upper().endswith("_2") else path.stem
    return normalize_tag(stem)


def _iter_images(root: Path):
    if not root.is_dir():
        return
    for item in root.rglob("*"):
        if (
            item.is_file()
            and not item.is_symlink()
            and not item.name.startswith(".")
            and item.suffix.casefold() in _IMAGE_EXTENSIONS
        ):
            yield item


def _same_bytes(first: Path, second: Path) -> bool:
    if first.stat().st_size != second.stat().st_size:
        return False
    def digest(path: Path):
        value = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                value.update(block)
        return value.digest()
    return digest(first) == digest(second)


def record_success(source_path: str, tag: str, category: str = "", *,
                   processing_root: str | os.PathLike[str] = paths.PROCESSING_DIR,
                   legacy_input_root: str | os.PathLike[str] | None = None,
                   processed_root: str | os.PathLike[str] = paths.PROCESSED_DIR) -> dict:
    """Move a successfully processed queue source into ``processed/``.

    Sources outside the two queue roots are left alone; this guarantees an
    accidental call can never move immutable capture/master files.
    """
    source = Path(source_path).resolve()
    processing = Path(processing_root).resolve()
    legacy_input = Path(legacy_input_root).resolve() if legacy_input_root else None
    processed = Path(processed_root).resolve()
    if not source.is_file():
        return {"moved": False, "reason": "source missing", "path": None}

    if source.is_relative_to(processing):
        relative = source.relative_to(processing)
    elif legacy_input is not None and source.is_relative_to(legacy_input):
        resolved = ornament_code_map.category_from_tag_code(tag)
        folder = resolved.label if resolved else (category or "LEGACY INPUT").replace("_", " ").upper()
        relative = Path(folder) / source.name
    else:
        return {"moved": False, "reason": "source is outside processing queues", "path": None}

    destination = processed / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _same_bytes(source, destination):
            # Idempotent recovery from a prior success that moved/copies state
            # only partially: the processed bytes are already safe, so remove
            # the redundant queue copy to restore the one-state invariant.
            source.unlink()
            _remove_empty_parents(
                source.parent,
                processing if source.is_relative_to(processing) else legacy_input,
            )
            return {"moved": True, "reason": "already processed", "path": str(destination)}
        raise FileExistsError(f"Processed destination differs: {destination}")
    os.rename(source, destination)
    _remove_empty_parents(source.parent, processing if source.is_relative_to(processing) else legacy_input)
    return {"moved": True, "reason": "", "path": str(destination)}


def _remove_empty_parents(start: Path, stop: Path | None):
    if stop is None:
        return
    current = start
    while current != stop:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _load_json(path: Path, default):
    if not path.is_file():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


@dataclass(frozen=True, slots=True)
class ResetPreview:
    tags: tuple[str, ...]
    processed_files: tuple[str, ...]
    progress_records: int
    catalogue_records: int
    conflicts: tuple[str, ...]

    def as_dict(self):
        return {
            "tags": list(self.tags),
            "processed_files": list(self.processed_files),
            "processed_file_count": len(self.processed_files),
            "progress_records": self.progress_records,
            "catalogue_records": self.catalogue_records,
            "conflicts": list(self.conflicts),
            "can_reset": not self.conflicts and bool(
                self.processed_files or self.progress_records or self.catalogue_records
            ),
        }


def preview_reset(tags: tuple[str, ...] | None, *,
                  base_dir: str | os.PathLike[str] | None = None,
                  processing_root: str | os.PathLike[str] = paths.PROCESSING_DIR,
                  processed_root: str | os.PathLike[str] = paths.PROCESSED_DIR,
                  db_path: str | os.PathLike[str] | None = None) -> ResetPreview:
    base = Path(base_dir or Path(__file__).parent)
    processing = Path(processing_root).resolve()
    processed = Path(processed_root).resolve()
    wanted = set(tags) if tags is not None else None
    files: list[str] = []
    conflicts: list[str] = []
    discovered_tags: set[str] = set(wanted or ())
    for item in _iter_images(processed) or ():
        tag = _tag_for_file(item)
        if wanted is not None and tag not in wanted:
            continue
        relative = item.relative_to(processed)
        files.append(str(relative).replace(os.sep, "/"))
        discovered_tags.add(tag)
        destination = processing / relative
        if destination.exists():
            conflicts.append(str(relative).replace(os.sep, "/"))

    progress_count = 0
    for path_string in glob.glob(str(base / "data" / "progress_*.json")):
        data = _load_json(Path(path_string), {})
        progress_count += sum(
            1 for record in data.values()
            if wanted is None or normalize_tag(str(record.get("label", ""))) in wanted
        )

    database = _load_json(Path(db_path or (base / "data" / "catalogue_db.json")), {"entries": []})
    catalogue_count = sum(
        1 for entry in database.get("entries", [])
        if wanted is None or normalize_tag(str(entry.get("label", ""))) in wanted
    )
    return ResetPreview(
        tags=tuple(sorted(discovered_tags)),
        processed_files=tuple(sorted(files, key=str.casefold)),
        progress_records=progress_count,
        catalogue_records=catalogue_count,
        conflicts=tuple(sorted(conflicts, key=str.casefold)),
    )


def apply_reset(tags: tuple[str, ...] | None, *,
                base_dir: str | os.PathLike[str] | None = None,
                processing_root: str | os.PathLike[str] = paths.PROCESSING_DIR,
                processed_root: str | os.PathLike[str] = paths.PROCESSED_DIR,
                db_path: str | os.PathLike[str] | None = None) -> dict:
    """Apply a previewed reset with rollback and a timestamped memory backup."""
    with _LOCK:
        base = Path(base_dir or Path(__file__).parent)
        processing = Path(processing_root).resolve()
        processed = Path(processed_root).resolve()
        database_path = Path(db_path or (base / "data" / "catalogue_db.json"))
        preview = preview_reset(
            tags, base_dir=base, processing_root=processing,
            processed_root=processed, db_path=database_path,
        )
        if preview.conflicts:
            raise FileExistsError("Processing destination already exists: " + preview.conflicts[0])

        stamp = time.strftime("%Y%m%d_%H%M%S")
        backup = base / "backups" / f"processed_reset_{stamp}"
        backup.mkdir(parents=True, exist_ok=False)
        memory_paths = [Path(p) for p in glob.glob(str(base / "data" / "progress_*.json"))]
        if database_path.is_file():
            memory_paths.append(database_path)
        for memory_path in memory_paths:
            shutil.copy2(memory_path, backup / memory_path.name)

        moved: list[tuple[Path, Path]] = []
        wanted = set(tags) if tags is not None else None
        try:
            for relative_string in preview.processed_files:
                relative = Path(relative_string)
                source = processed / relative
                destination = processing / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.rename(source, destination)
                moved.append((destination, source))

            for progress_path in [Path(p) for p in glob.glob(str(base / "data" / "progress_*.json"))]:
                data = _load_json(progress_path, {})
                kept = {
                    key: record for key, record in data.items()
                    if wanted is not None
                    and normalize_tag(str(record.get("label", ""))) not in wanted
                }
                _atomic_json(progress_path, kept)

            database = _load_json(database_path, {"entries": []})
            database["entries"] = [
                entry for entry in database.get("entries", [])
                if wanted is not None
                and normalize_tag(str(entry.get("label", ""))) not in wanted
            ]
            _atomic_json(database_path, database)
        except Exception:
            for current, original in reversed(moved):
                if current.exists() and not original.exists():
                    original.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(current, original)
            for saved in backup.iterdir():
                shutil.copy2(saved, base / saved.name)
            raise

        return {
            **preview.as_dict(),
            "moved_to_processing": len(moved),
            "backup": str(backup),
        }
