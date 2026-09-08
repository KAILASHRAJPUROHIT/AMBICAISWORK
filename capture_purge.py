"""Confirmed downstream purge while preserving immutable capture masters.

This module is imported only by the capture-memory admin routes.  It never
starts background work.  Callers must hold the live capture tool's process by
calling ``purge_folder_history``; that function acquires ``capture_tool._lock``
for the complete state transition and deletion.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parent
RAW_MIRROR_DIR = Path(
    os.environ.get(
        "AJ_RAW_MIRROR_DIR",
        r"C:\AradhanaSystems\projects\catalogue-capture\main\master backup",
    )
)
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_INVALID_TAG_CHARS = re.compile(r'[\\/:*?"<>|]')


class CapturePurgeError(RuntimeError):
    """The requested capture history cannot be purged safely."""


@dataclass(frozen=True, slots=True)
class PurgePreview:
    folder: str
    files: int
    primary_images: int
    tags: tuple[str, ...]
    dedup_records: int
    generated_files: tuple[str, ...]
    shared_tags_preserved: tuple[str, ...]
    active_categories: tuple[str, ...]
    folder_paths: tuple[str, ...]
    preserved_master_paths: tuple[str, ...]
    preserved_master_files: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _quick_folder_counts(folder: str, roots: dict[str, Path], tag_archive_name: str) -> tuple[int, int]:
    """Cheap per-folder file/primary-image counts across all roots.

    Deliberately does NOT call _shared_tag_stems or _generated_files — those
    each rescan every OTHER folder in every root, so calling them once per
    folder (as list_capture_histories used to, via the full purge preview)
    made the whole listing O(N^2) in folder count. Confirmed live: 24s for
    138 folders. This function only ever looks inside the one folder it was
    asked about, so building the full list stays linear. The expensive
    cross-folder analysis still runs, correctly, in preview_folder_history —
    but only on-demand for the one folder a user is actually about to purge,
    not for every folder on every admin-panel page load."""
    files = 0
    primary = 0
    for root in roots.values():
        directory = root / folder
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            files += 1
            if (
                path.parent.name.casefold() != tag_archive_name.casefold()
                and path.suffix.casefold() in _IMAGE_EXTENSIONS
            ):
                primary += 1
    return files, primary


def list_capture_histories(capture_tool) -> list[dict[str, Any]]:
    """List every known folder from disk or dedup memory."""

    dedup_counts: dict[str, int] = {}
    for record in capture_tool._load_dedup().values():
        if isinstance(record, dict):
            folder = record.get("folder")
            if folder:
                dedup_counts[folder] = dedup_counts.get(folder, 0) + 1

    roots = _folder_roots(capture_tool)
    folders = set(dedup_counts)
    for root in roots.values():
        if root.is_dir():
            folders.update(path.name for path in root.iterdir() if path.is_dir())

    histories = []
    for folder in sorted(folders, key=str.casefold):
        files, primary = _quick_folder_counts(folder, roots, capture_tool.TAG_ARCHIVE_DIRNAME)
        records = dedup_counts.get(folder, 0)
        if files == 0 and records == 0:
            continue
        histories.append(
            {
                "folder": folder,
                "records": records,
                "files": files,
                "primary_images": primary,
            }
        )
    return histories


def preview_folder_history(capture_tool, folder: str) -> PurgePreview:
    folder = _validated_folder_name(folder)
    roots = _folder_roots(capture_tool)
    dedup = capture_tool._load_dedup()
    dedup_tags = {
        tag
        for tag, record in dedup.items()
        if isinstance(record, dict) and record.get("folder") == folder
    }
    exact_dirs = [root / folder for root in roots.values()]
    existing_dirs = [path for path in exact_dirs if path.is_dir()]
    if not existing_dirs and not dedup_tags:
        raise CapturePurgeError(f"No capture history exists for folder {folder!r}")

    safe_stems = set()
    primary_count = 0
    file_count = 0
    preserved_file_count = 0
    immutable_roots = {
        root.resolve()
        for name, root in roots.items()
        if name in _IMMUTABLE_ROOT_NAMES
    }
    preserved_dirs = [
        path for path in existing_dirs if path.parent.resolve() in immutable_roots
    ]
    purgeable_dirs = [path for path in existing_dirs if path not in preserved_dirs]
    for directory in existing_dirs:
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if directory in preserved_dirs:
                preserved_file_count += 1
            else:
                file_count += 1
            if (
                path.parent.name.casefold()
                != capture_tool.TAG_ARCHIVE_DIRNAME.casefold()
                and path.suffix.casefold() in _IMAGE_EXTENSIONS
            ):
                primary_count += 1
                safe_stems.add(_base_tag_stem(path.stem))
    safe_stems.update(_safe_tag(tag) for tag in dedup_tags)

    shared_stems = _shared_tag_stems(
        roots=roots,
        excluded_folder=folder,
        candidate_stems=safe_stems,
        tag_archive_name=capture_tool.TAG_ARCHIVE_DIRNAME,
    )
    removable_stems = safe_stems - shared_stems
    generated = _generated_files(removable_stems)
    active = tuple(
        category
        for category, current in capture_tool._load_tray_state().items()
        if current == folder
    )
    return PurgePreview(
        folder=folder,
        files=file_count + len(generated),
        primary_images=primary_count,
        tags=tuple(sorted(safe_stems, key=str.casefold)),
        dedup_records=len(dedup_tags),
        generated_files=tuple(str(path) for path in generated),
        shared_tags_preserved=tuple(sorted(shared_stems, key=str.casefold)),
        active_categories=active,
        folder_paths=tuple(str(path) for path in purgeable_dirs),
        preserved_master_paths=tuple(str(path) for path in preserved_dirs),
        preserved_master_files=preserved_file_count,
    )


def purge_folder_history(capture_tool, folder: str) -> dict[str, Any]:
    """Delete downstream history while retaining every raw master file."""

    folder = _validated_folder_name(folder)
    with capture_tool._lock:
        preview = preview_folder_history(capture_tool, folder)
        advanced = _advance_active_trays(capture_tool, folder)
        deleted_files = 0
        deleted_folders = []
        errors = []

        for raw_path in preview.generated_files:
            path = Path(raw_path)
            try:
                path.unlink()
                deleted_files += 1
                _remove_empty_parents(path.parent, _containing_generated_root(path))
            except FileNotFoundError:
                pass
            except OSError as exc:
                errors.append(f"{path}: {exc}")

        for raw_path in preview.folder_paths:
            path = Path(raw_path)
            try:
                deleted_files += sum(1 for item in path.rglob("*") if item.is_file())
                shutil.rmtree(path)
                deleted_folders.append(str(path))
            except FileNotFoundError:
                pass
            except OSError as exc:
                errors.append(f"{path}: {exc}")

        if errors:
            return {
                "ok": False,
                "folder": folder,
                "error": "Purge was incomplete",
                "errors": errors,
                "deleted_files": deleted_files,
                "deleted_folders": deleted_folders,
                "advanced_trays": advanced,
            }

        dedup = capture_tool._load_dedup()
        removed_tags = [
            tag
            for tag, record in dedup.items()
            if isinstance(record, dict) and record.get("folder") == folder
        ]
        for tag in removed_tags:
            del dedup[tag]
        if removed_tags:
            capture_tool._atomic_write_json(capture_tool.DEDUP_PATH, dedup)

        _record_purge_tombstone(
            folder=folder,
            deleted_files=deleted_files,
            removed_tags=removed_tags,
            shared_tags=preview.shared_tags_preserved,
        )
        return {
            "ok": True,
            "folder": folder,
            "deleted_files": deleted_files,
            "deleted_folders": deleted_folders,
            "removed_dedup_records": len(removed_tags),
            "advanced_trays": advanced,
            "shared_tags_preserved": list(preview.shared_tags_preserved),
            "preserved_master_paths": list(preview.preserved_master_paths),
            "preserved_master_files": preview.preserved_master_files,
        }


def _folder_roots(capture_tool) -> dict[str, Path]:
    import paths

    candidates = (
        ("capture_intake", Path(capture_tool.CAPTURE_ROOT)),
        ("capture", Path(paths.CAPTURE_DIR)),
        ("processing", Path(paths.PROCESSING_DIR)),
        ("processed", Path(paths.PROCESSED_DIR)),
        ("needs_review", Path(paths.NEEDS_REVIEW_DIR)),
        ("rejected", Path(paths.REJECTED_DIR)),
        ("legacy_input", BASE / "input"),
        ("legacy_needs_review", BASE / "_needs_review"),
        ("legacy_rejected", BASE / "Reject"),
        ("raw_mirror", RAW_MIRROR_DIR),
    )
    roots: dict[str, Path] = {}
    seen: set[str] = set()
    for name, candidate in candidates:
        identity = os.path.normcase(os.path.abspath(candidate))
        if identity not in seen:
            roots[name] = candidate
            seen.add(identity)
    return roots


_IMMUTABLE_ROOT_NAMES = frozenset(
    {"capture_intake", "capture", "raw_mirror"}
)


def _generated_roots() -> tuple[Path, ...]:
    import paths

    candidates = (Path(paths.OUTPUT_DIR), BASE / "output_aradhana")
    roots = []
    seen = set()
    for candidate in candidates:
        identity = os.path.normcase(os.path.abspath(candidate))
        if identity not in seen:
            roots.append(candidate)
            seen.add(identity)
    return tuple(roots)


def _generated_files(stems: set[str]) -> tuple[Path, ...]:
    if not stems:
        return ()
    matches = []
    for root in _generated_roots():
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.casefold() in _IMAGE_EXTENSIONS
                and _base_tag_stem(path.stem) in stems
            ):
                matches.append(path)
    return tuple(sorted(matches, key=lambda path: str(path).casefold()))


def _shared_tag_stems(
    *,
    roots: dict[str, Path],
    excluded_folder: str,
    candidate_stems: set[str],
    tag_archive_name: str,
) -> set[str]:
    shared = set()
    if not candidate_stems:
        return shared
    for root in roots.values():
        if not root.is_dir():
            continue
        for directory in root.iterdir():
            if not directory.is_dir() or directory.name == excluded_folder:
                continue
            for path in directory.rglob("*"):
                if (
                    path.is_file()
                    and path.parent.name.casefold() != tag_archive_name.casefold()
                    and path.suffix.casefold() in _IMAGE_EXTENSIONS
                ):
                    stem = _base_tag_stem(path.stem)
                    if stem in candidate_stems:
                        shared.add(stem)
    return shared


def _advance_active_trays(capture_tool, folder: str) -> dict[str, str]:
    """Reassign any category currently pointing at the just-forgotten
    folder to a fresh tray. Deliberately does NOT create the new folder on
    disk — that happens only at the moment of a real capture (see
    start_new_tray/save_pair) — otherwise every Forget of an empty tray
    would immediately manifest a brand-new empty one in its place, which is
    exactly the "something keeps recreating them" symptom this was
    causing."""
    state = capture_tool._load_tray_state()
    advanced = {}
    for category, current in list(state.items()):
        if current != folder:
            continue
        if category == capture_tool.TEST_CATEGORY:
            del state[category]
            continue
        # _next_tray_number reads tray state fresh from disk each call, so
        # persist each reassignment before computing the next one — two
        # categories sharing this same forgotten folder must never be
        # handed the same "next" number.
        capture_tool._save_tray_state(state)
        number = capture_tool._next_tray_number()
        next_folder = capture_tool._tray_folder_name(category, number)
        state[category] = next_folder
        advanced[category] = next_folder
    if advanced or folder not in state.values():
        capture_tool._save_tray_state(state)
    return advanced


def _record_purge_tombstone(
    *,
    folder: str,
    deleted_files: int,
    removed_tags: list[str],
    shared_tags: tuple[str, ...],
) -> None:
    """Keep only a non-image audit that a destructive action occurred."""

    path = BASE / "data" / "capture_purge_audit.jsonl"
    record = {
        "folder": folder,
        "deleted_files": deleted_files,
        "removed_tag_count": len(removed_tags),
        "shared_tags_preserved": list(shared_tags),
        "ts": __import__("time").time(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _validated_folder_name(folder: str) -> str:
    value = (folder or "").strip()
    if (
        not value
        or value in {".", ".."}
        or Path(value).name != value
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise CapturePurgeError(f"Invalid capture folder name: {folder!r}")
    return value


def _safe_tag(tag: str) -> str:
    return _INVALID_TAG_CHARS.sub("_", tag.strip())


def _base_tag_stem(stem: str) -> str:
    stem = re.sub(r"_tag$", "", stem, flags=re.IGNORECASE)
    return re.sub(r"_2$", "", stem)


def _containing_generated_root(path: Path) -> Path:
    resolved = path.resolve()
    for root in _generated_roots():
        root_resolved = root.resolve()
        if resolved == root_resolved or root_resolved in resolved.parents:
            return root_resolved
    raise CapturePurgeError(f"Generated path is outside configured roots: {path}")


def _remove_empty_parents(path: Path, stop: Path) -> None:
    current = path
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
