"""Daily stock delta, sold-item archiving, and new-capture notifications.

The newest dated Stock/DDMMYYYY.xls(x) file is authoritative.  Reconciliation
only runs after both the newest and immediately-previous workbooks validate.
It is idempotent across the catalogue and isolated capture server processes.
"""
from __future__ import annotations

import contextlib
import glob
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import paths
import stock_excel


BASE = Path(__file__).resolve().parent
STATE_PATH = BASE / "data" / "stock_reconciliation_state.json"
AUDIT_PATH = BASE / "data" / "stock_reconciliation_audit.jsonl"
LOCK_PATH = BASE / "data" / ".stock_reconciliation.lock"
VERSION = 1
MAX_SOLD_TAGS_PER_RUN = 500
LOCK_WAIT_SECONDS = 15.0
STALE_LOCK_SECONDS = 300.0
_THREAD_LOCK = threading.RLock()
_CURRENT_TAG_CACHE_LOCK = threading.Lock()
_CURRENT_TAG_CACHE: dict[str, Any] = {"signature": None, "tags": frozenset()}
_STOCK_TAG_RE = re.compile(r"^[A-Z][A-Z0-9-]*[0-9](?:_[0-9]+)+$")


class StockReconciliationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    previous_workbook: str | None
    current_workbook: str | None
    current_tag_count: int
    sold_tags: tuple[str, ...]
    new_tags: tuple[str, ...]
    moved_files: int
    deleted_files: int
    removed_memory_records: int
    reconciled: bool
    signature: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalise_tag(value: str) -> str:
    return stock_excel.safe_filename_label(value or "").strip().upper()


def _is_stock_tag(value: str) -> bool:
    return bool(_STOCK_TAG_RE.fullmatch(_normalise_tag(value)))


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


@contextlib.contextmanager
def data_lock(*, timeout: float = LOCK_WAIT_SECONDS):
    """Cross-process guard shared by reconciliation and capture writes."""

    deadline = time.monotonic() + max(0.1, timeout)
    descriptor = None
    with _THREAD_LOCK:
        while descriptor is None:
            try:
                descriptor = os.open(
                    LOCK_PATH,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                payload = json.dumps(
                    {"pid": os.getpid(), "created_at": time.time()},
                    sort_keys=True,
                ).encode("utf-8")
                os.write(descriptor, payload)
                os.fsync(descriptor)
            except FileExistsError:
                try:
                    stale = time.time() - LOCK_PATH.stat().st_mtime > STALE_LOCK_SECONDS
                except OSError:
                    stale = False
                if stale:
                    try:
                        LOCK_PATH.unlink()
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise StockReconciliationError(
                        "Timed out waiting for the stock reconciliation lock"
                    )
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                os.close(descriptor)
            finally:
                try:
                    LOCK_PATH.unlink()
                except FileNotFoundError:
                    pass


def _workbook_signature(previous: Path, current: Path) -> str:
    value = hashlib.sha256()
    for path in (previous, current):
        stat = path.stat()
        value.update(str(path.resolve()).casefold().encode("utf-8"))
        value.update(str(stat.st_size).encode("ascii"))
        value.update(str(stat.st_mtime_ns).encode("ascii"))
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                value.update(block)
    return value.hexdigest()


def _source_identity(previous: Path, current: Path) -> str:
    """Cheap change detector; full workbook hashing follows only on change."""
    value = hashlib.sha256()
    for path in (previous, current):
        stat = path.stat()
        value.update(str(path.resolve()).casefold().encode("utf-8"))
        value.update(str(stat.st_size).encode("ascii"))
        value.update(str(stat.st_mtime_ns).encode("ascii"))
    return value.hexdigest()


def _candidate_pair(stock_dir: Path) -> tuple[Path, Path]:
    workbooks = stock_excel.discover_stock_workbooks(stock_dir)
    if len(workbooks) < 2:
        raise StockReconciliationError(
            "At least two dated stock workbooks are required for reconciliation"
        )
    previous, current = workbooks[-2], workbooks[-1]
    previous_date = stock_excel.stock_date_from_filename(previous)
    current_date = stock_excel.stock_date_from_filename(current)
    if previous_date is None or current_date is None or current_date <= previous_date:
        raise StockReconciliationError("Stock workbook dates are not strictly increasing")
    return previous, current


def _safe_label_map(labels: Iterable[str], source: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for label in labels:
        safe = _normalise_tag(label)
        if not _is_stock_tag(safe):
            raise StockReconciliationError(
                f"{source.name}: invalid stock tag {label!r}"
            )
        prior = result.get(safe)
        if prior is not None and prior.casefold() != label.casefold():
            raise StockReconciliationError(
                f"{source.name}: labels {prior!r} and {label!r} map to {safe!r}"
            )
        result[safe] = label
    if not result:
        raise StockReconciliationError(f"{source.name} contains no stock tags")
    return result


def _validated_pair(stock_dir: Path) -> tuple[Path, Path, dict[str, str], dict[str, str]]:
    previous, current = _candidate_pair(stock_dir)

    previous_inventory = stock_excel.load_stock_label_inventory(previous)
    current_inventory = stock_excel.load_stock_label_inventory(current)
    # Compact daily exports intentionally contain only ItemName/Label No.
    # load_stock_label_inventory validates readability, the required label
    # column, non-empty content, and duplicate labels. _safe_label_map above
    # additionally validates every tag and filename-normalisation collision.
    return (
        previous,
        current,
        _safe_label_map(previous_inventory.labels, previous),
        _safe_label_map(current_inventory.labels, current),
    )


def _active_roots(base: Path = BASE) -> tuple[Path, ...]:
    candidates = (
        base / "capture_intake",
        Path(paths.CAPTURE_DIR),
        base / "input",
        Path(paths.PROCESSING_DIR),
        Path(paths.PROCESSED_DIR),
        Path(paths.OUTPUT_DIR),
        base / "output_aradhana",
        Path(paths.NEEDS_REVIEW_DIR),
        Path(paths.REJECTED_DIR),
        base / "_needs_review",
        base / "Reject",
    )
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        identity = os.path.normcase(str(resolved))
        if identity not in seen:
            roots.append(resolved)
            seen.add(identity)
    return tuple(roots)


def _memory_paths(base: Path = BASE) -> tuple[Path, ...]:
    values = [
        base / "data" / "capture_dedup.json",
        base / "data" / "catalogue_db.json",
        base / "data" / "review_state.json",
        base / "data" / "feedback.jsonl",
    ]
    values.extend(Path(path) for path in glob.glob(str(base / "data" / "progress_*.json")))
    return tuple(path for path in values if path.is_file())


def _tags_from_memory(base: Path = BASE) -> set[str]:
    tags: set[str] = set()
    dedup = _load_json(base / "data" / "capture_dedup.json", {})
    if isinstance(dedup, dict):
        tags.update(_normalise_tag(tag) for tag in dedup if _is_stock_tag(tag))
    database = _load_json(base / "data" / "catalogue_db.json", {"entries": []})
    if isinstance(database, dict):
        for entry in database.get("entries", []):
            label = entry.get("label", "") if isinstance(entry, dict) else ""
            if _is_stock_tag(label):
                tags.add(_normalise_tag(label))
    for path in (base / "data" / "review_state.json",):
        state = _load_json(path, {})
        if isinstance(state, dict):
            tags.update(_normalise_tag(tag) for tag in state if _is_stock_tag(tag))
    for progress_path in (Path(path) for path in glob.glob(str(base / "data" / "progress_*.json"))):
        progress = _load_json(progress_path, {})
        if not isinstance(progress, dict):
            continue
        for record in progress.values():
            label = record.get("label", "") if isinstance(record, dict) else ""
            if _is_stock_tag(label):
                tags.add(_normalise_tag(label))
    return tags


def _tag_for_path(path: Path, known_tags: tuple[str, ...]) -> str | None:
    parts = {_normalise_tag(part) for part in path.parts}
    for tag in known_tags:
        if tag in parts:
            return tag
    stem = path.stem.lstrip(".").upper()
    for tag in known_tags:
        if stem == tag or any(stem.startswith(tag + sep) for sep in ("_", ".", "-")):
            return tag
    return None


def _unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}__{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise StockReconciliationError(f"Unable to allocate sold archive name for: {path}")


def _move_sold_files(
    sold: set[str],
    all_known: set[str],
    *,
    roots: tuple[Path, ...],
    sold_root: Path,
) -> tuple[int, int, tuple[dict[str, str], ...]]:
    if not sold:
        return 0, 0, ()
    known_longest = tuple(sorted(all_known, key=lambda value: (-len(value), value)))
    targets: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            if _tag_for_path(path, known_longest) in sold:
                targets.append(path)

    unique_targets = sorted(set(targets), key=lambda path: str(path).casefold())
    sold_root = sold_root.resolve()
    planned: list[tuple[Path, Path, int]] = []
    root_labels = {root: f"{index:02d}_{root.name or 'root'}" for index, root in enumerate(roots, 1)}
    for path in unique_targets:
        resolved = path.resolve()
        owner = next((root for root in roots if resolved.is_relative_to(root)), None)
        if owner is None:
            raise StockReconciliationError(f"Refusing unconfined move: {path}")
        relative = resolved.relative_to(owner)
        destination = _unique_destination(sold_root / root_labels[owner] / relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.resolve().is_relative_to(sold_root):
            raise StockReconciliationError(f"Refusing unconfined sold destination: {destination}")
        planned.append((resolved, destination, resolved.stat().st_size))

    moved: list[tuple[Path, Path, int]] = []
    try:
        for source, destination, size in planned:
            shutil.move(str(source), str(destination))
            moved.append((source, destination, size))
    except Exception as exc:
        rollback_errors: list[str] = []
        for source, destination, _ in reversed(moved):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            except Exception as rollback_exc:
                rollback_errors.append(f"{destination}: {rollback_exc}")
        detail = f"; rollback failures: {' | '.join(rollback_errors)}" if rollback_errors else ""
        raise StockReconciliationError(f"Sold archive move failed: {exc}{detail}") from exc

    records = tuple({"source": str(source), "destination": str(destination)} for source, destination, _ in moved)
    return len(moved), sum(size for _, _, size in moved), records


def _backup_memory(paths_to_backup: tuple[Path, ...], current: Path, base: Path) -> Path | None:
    if not paths_to_backup:
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = base / "backups" / f"stock_reconciliation_{current.stem}_{stamp}_{uuid.uuid4().hex[:6]}"
    backup.mkdir(parents=True, exist_ok=False)
    for path in paths_to_backup:
        shutil.copy2(path, backup / path.name)
    return backup


def _purge_memory(
    sold: set[str], *, current: Path, base: Path = BASE
) -> tuple[int, str | None]:
    if not sold:
        return 0, None
    existing = _memory_paths(base)
    backup = _backup_memory(existing, current, base)
    removed = 0

    dedup_path = base / "data" / "capture_dedup.json"
    dedup = _load_json(dedup_path, {})
    if isinstance(dedup, dict):
        kept = {}
        for key, value in dedup.items():
            if _normalise_tag(key) in sold:
                removed += 1
            else:
                kept[key] = value
        if kept != dedup:
            _atomic_json(dedup_path, kept)

    database_path = base / "data" / "catalogue_db.json"
    database = _load_json(database_path, {"entries": []})
    if isinstance(database, dict):
        entries = list(database.get("entries", []))
        kept_entries = [
            entry for entry in entries
            if not isinstance(entry, dict)
            or _normalise_tag(entry.get("label", "")) not in sold
        ]
        removed += len(entries) - len(kept_entries)
        if kept_entries != entries:
            database["entries"] = kept_entries
            _atomic_json(database_path, database)

    review_path = base / "data" / "review_state.json"
    review = _load_json(review_path, {})
    if isinstance(review, dict):
        kept_review = {key: value for key, value in review.items() if _normalise_tag(key) not in sold}
        removed += len(review) - len(kept_review)
        if kept_review != review:
            _atomic_json(review_path, kept_review)

    for progress_path in (Path(path) for path in glob.glob(str(base / "data" / "progress_*.json"))):
        progress = _load_json(progress_path, {})
        if not isinstance(progress, dict):
            continue
        kept_progress = {
            key: value for key, value in progress.items()
            if not isinstance(value, dict)
            or _normalise_tag(value.get("label", "")) not in sold
        }
        removed += len(progress) - len(kept_progress)
        if kept_progress != progress:
            _atomic_json(progress_path, kept_progress)

    feedback_path = base / "data" / "feedback.jsonl"
    if feedback_path.is_file():
        kept_lines: list[str] = []
        feedback_removed = 0
        with feedback_path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                try:
                    row = json.loads(raw_line)
                except json.JSONDecodeError:
                    kept_lines.append(raw_line)
                    continue
                if isinstance(row, dict) and _normalise_tag(row.get("label", "")) in sold:
                    feedback_removed += 1
                else:
                    kept_lines.append(raw_line)
        if feedback_removed:
            temporary = feedback_path.with_name(feedback_path.name + f".{os.getpid()}.tmp")
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.writelines(kept_lines)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, feedback_path)
            removed += feedback_removed

    return removed, str(backup) if backup else None


def _item_details(labels: dict[str, str]) -> list[dict[str, str]]:
    try:
        import ornament_code_map
    except Exception:
        ornament_code_map = None
    result = []
    for safe_tag, original in sorted(labels.items()):
        category = "Unknown category"
        if ornament_code_map is not None:
            resolved = ornament_code_map.category_from_tag_code(original)
            if resolved is not None:
                category = resolved.label
        result.append({"label": original, "safe_tag": safe_tag, "category": category})
    return result


def _captured_tags(current_tags: set[str], base: Path = BASE) -> set[str]:
    """Find usable raw jewellery photos from disk, not capture memory.

    Dedup memory can be missing or stale. The master raw tree is authoritative.
    Archived tag photos and operator-voided captures do not count.
    """
    import capture_voids

    root = (base / "capture_intake").resolve()
    if not root.is_dir() or not current_tags:
        return set()
    voids = capture_voids.load_void_registry(base / "data" / "capture_voids.json")
    known_longest = tuple(sorted(current_tags, key=lambda value: (-len(value), value)))
    captured: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if "_tag_archive" in relative.parts:
            continue
        if path.suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        if relative.as_posix() in voids:
            continue
        tag = _tag_for_path(path, known_longest)
        if tag is not None:
            captured.add(tag)
    return captured


def _natural_tag_key(value: str) -> tuple[Any, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", value)
        if part
    )


def _capture_recommendations(
    current_items: list[dict[str, str]], captured: set[str]
) -> list[dict[str, Any]]:
    """Started categories first; least remaining first within each tier."""
    grouped: dict[str, dict[str, Any]] = {}
    for item in current_items:
        category = item.get("category") or "Unknown category"
        group = grouped.setdefault(
            category,
            {"category": category, "total": 0, "captured": 0, "pending": []},
        )
        group["total"] += 1
        if item["safe_tag"] in captured:
            group["captured"] += 1
        else:
            group["pending"].append(item)

    recommendations: list[dict[str, Any]] = []
    for group in grouped.values():
        if not group["pending"]:
            continue
        pending_items = sorted(
            group["pending"], key=lambda item: _natural_tag_key(item["safe_tag"])
        )
        remaining = len(pending_items)
        recommendations.append({
            "category": group["category"],
            "total": group["total"],
            "captured": group["captured"],
            "remaining": remaining,
            "started": group["captured"] > 0,
            "next_tag": pending_items[0]["label"],
            "next_safe_tag": pending_items[0]["safe_tag"],
        })
    recommendations.sort(key=lambda row: (
        not row["started"],
        row["remaining"],
        row["category"].casefold(),
        _natural_tag_key(row["next_safe_tag"]),
    ))
    for priority, row in enumerate(recommendations, start=1):
        row["priority"] = priority
    return recommendations


def _append_audit(record: dict[str, Any], *, path: Path = AUDIT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def ensure_reconciled(
    *,
    stock_dir: str | os.PathLike[str] = stock_excel.STOCK_DIR,
    base_dir: str | os.PathLike[str] = BASE,
    state_path: str | os.PathLike[str] = STATE_PATH,
    roots: tuple[Path, ...] | None = None,
) -> ReconciliationResult:
    base = Path(base_dir).resolve()
    state_file = Path(state_path)
    with data_lock():
        state = _load_json(state_file, {})
        candidate_previous, candidate_current = _candidate_pair(Path(stock_dir))
        source_identity = _source_identity(candidate_previous, candidate_current)
        if state.get("version") == VERSION and state.get("source_identity") == source_identity:
            if not isinstance(state.get("current_items"), list):
                _, _, _, current_tags = _validated_pair(Path(stock_dir))
                state["current_items"] = _item_details(current_tags)
                _atomic_json(state_file, state)
            return ReconciliationResult(
                previous_workbook=state.get("previous_workbook"),
                current_workbook=state.get("current_workbook"),
                current_tag_count=int(state.get("current_tag_count", 0)),
                sold_tags=tuple(state.get("sold_tags", [])),
                new_tags=tuple(item["safe_tag"] for item in state.get("pending_new", [])),
                moved_files=int(state.get("moved_files", 0)),
                deleted_files=int(state.get("deleted_files", 0)),
                removed_memory_records=int(state.get("removed_memory_records", 0)),
                reconciled=False,
                signature=state.get("signature"),
            )

        previous, current, previous_tags, current_tags = _validated_pair(Path(stock_dir))
        signature = _workbook_signature(previous, current)

        daily_sold = set(previous_tags) - set(current_tags)
        if len(daily_sold) > MAX_SOLD_TAGS_PER_RUN:
            raise StockReconciliationError(
                f"Safety stop: {len(daily_sold)} sold tags exceeds the "
                f"{MAX_SOLD_TAGS_PER_RUN}-tag unattended limit"
            )
        added = set(current_tags) - set(previous_tags)

        known_active = _tags_from_memory(base)
        # Exact business rule: present in the previous workbook and absent from
        # the newest validated workbook means sold. Never infer sold from memory.
        purge_tags = set(daily_sold)
        purge_tags = {tag for tag in purge_tags if _is_stock_tag(tag)}
        all_known = set(previous_tags) | set(current_tags) | known_active
        active_roots = roots if roots is not None else _active_roots(base)
        sold_archive = base / "sold" / current.stem
        moved, moved_bytes, moved_paths = _move_sold_files(
            purge_tags, all_known, roots=active_roots, sold_root=sold_archive
        )
        removed_memory, backup = _purge_memory(purge_tags, current=current, base=base)

        prior_pending = {
            item.get("safe_tag"): item
            for item in state.get("pending_new", [])
            if isinstance(item, dict) and item.get("safe_tag") in current_tags
        }
        pending_map = {
            **prior_pending,
            **{item["safe_tag"]: item for item in _item_details({tag: current_tags[tag] for tag in added})},
        }
        pending_new = [pending_map[tag] for tag in sorted(pending_map)]
        completed_at = time.time()
        new_state = {
            "version": VERSION,
            "signature": signature,
            "source_identity": source_identity,
            "previous_workbook": previous.name,
            "current_workbook": current.name,
            "current_tag_count": len(current_tags),
            "sold_tags": sorted(purge_tags),
            "daily_sold_tags": sorted(daily_sold),
            "new_tags": sorted(added),
            "current_items": _item_details(current_tags),
            "pending_new": pending_new,
            "moved_files": moved,
            "moved_bytes": moved_bytes,
            "sold_archive": str(sold_archive),
            "deleted_files": 0,
            "deleted_bytes": 0,
            "removed_memory_records": removed_memory,
            "memory_backup": backup,
            "notification_ready": True,
            "completed_at": completed_at,
        }
        _atomic_json(state_file, new_state)
        _append_audit(
            {
                "previous_workbook": previous.name,
                "current_workbook": current.name,
                "signature": signature,
                "daily_sold_count": len(daily_sold),
                "purged_tag_count": len(purge_tags),
                "new_tag_count": len(added),
                "moved_files": moved,
                "moved_bytes": moved_bytes,
                "sold_archive": str(sold_archive),
                "deleted_files": 0,
                "deleted_bytes": 0,
                "removed_memory_records": removed_memory,
                "moved_paths": list(moved_paths),
                "completed_at": completed_at,
            },
            path=base / AUDIT_PATH.name,
        )
        return ReconciliationResult(
            previous_workbook=previous.name,
            current_workbook=current.name,
            current_tag_count=len(current_tags),
            sold_tags=tuple(sorted(purge_tags)),
            new_tags=tuple(sorted(added)),
            moved_files=moved,
            deleted_files=0,
            removed_memory_records=removed_memory,
            reconciled=True,
            signature=signature,
        )


def status(*, reconcile: bool = True, **kwargs) -> dict[str, Any]:
    base = Path(kwargs.get("base_dir", BASE)).resolve()
    state_file = Path(kwargs.get("state_path", STATE_PATH))
    state = _load_json(state_file, {})
    if reconcile:
        result = ensure_reconciled(**kwargs)
        state = _load_json(state_file, {})
    else:
        result = ReconciliationResult(
            previous_workbook=state.get("previous_workbook"),
            current_workbook=state.get("current_workbook"),
            current_tag_count=int(state.get("current_tag_count", 0)),
            sold_tags=tuple(state.get("sold_tags", [])),
            new_tags=tuple(state.get("new_tags", [])),
            moved_files=int(state.get("moved_files", 0)),
            deleted_files=int(state.get("deleted_files", 0)),
            removed_memory_records=int(state.get("removed_memory_records", 0)),
            reconciled=False,
            signature=state.get("signature"),
        )
    current_items = [
        item for item in state.get("current_items", [])
        if isinstance(item, dict) and _is_stock_tag(item.get("safe_tag", ""))
    ]
    current_tags = {item["safe_tag"] for item in current_items}
    captured = _captured_tags(current_tags, base)
    pending = [
        item for item in current_items if item.get("safe_tag") not in captured
    ]
    new_tags = set(state.get("new_tags", []))
    recommendations = _capture_recommendations(current_items, captured)
    return {
        "ok": True,
        **result.as_dict(),
        "pending_capture_count": len(pending),
        "pending_capture": pending,
        "new_pending_capture_count": sum(
            item.get("safe_tag") in new_tags for item in pending
        ),
        "captured_raw_count": len(captured),
        "next_capture": recommendations[0] if recommendations else None,
        "capture_recommendations": recommendations,
        "recommendation_rule": (
            "Started categories first, ordered by fewest remaining items; "
            "then unstarted categories by fewest items."
        ),
        "completed_at": state.get("completed_at"),
        "sold_archive": state.get("sold_archive"),
        "notification_ready": bool(state.get("notification_ready", False)),
    }


def is_current_tag(label: str, *, stock_dir: str | os.PathLike[str] = stock_excel.STOCK_DIR) -> bool:
    """Fail closed for a readable stock file; fail open if stock is unavailable."""

    normalised = _normalise_tag(label)
    if not _is_stock_tag(normalised):
        return True
    try:
        current = stock_excel.latest_stock_workbook(stock_dir)
        stat = current.stat()
        signature = (str(current.resolve()).casefold(), stat.st_size, stat.st_mtime_ns)
        with _CURRENT_TAG_CACHE_LOCK:
            if _CURRENT_TAG_CACHE["signature"] != signature:
                inventory = stock_excel.load_stock_label_inventory(current)
                validated = _safe_label_map(inventory.labels, current)
                _CURRENT_TAG_CACHE["tags"] = frozenset(validated)
                _CURRENT_TAG_CACHE["signature"] = signature
            current_tags = _CURRENT_TAG_CACHE["tags"]
        return normalised in current_tags
    except Exception:
        return True
