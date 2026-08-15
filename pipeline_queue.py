"""Safe, additive intake mirroring and lifecycle transitions.

The live ``capture_intake`` tree is an immutable source.  This module can copy
stable files into the target ``capture`` master and queue primary jewellery
images in oldest-received-first order.  Archived tag photos are preserved in
the master but never queued for generation.

The module is standalone: no daemon imports it and no production directory is
created until an explicit caller invokes ``sync_intake_once``.
"""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import capture_voids


TAG_ARCHIVE_DIRNAME = "_tag_archive"
PROCESSABLE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
DEFAULT_STABLE_AGE_SECONDS = 10.0


class PipelineQueueError(RuntimeError):
    """Base class for intake and lifecycle failures."""


class FileConflictError(PipelineQueueError):
    """A destination path exists with bytes different from the master."""


class StateConflictError(PipelineQueueError):
    """One item exists in more than one lifecycle directory."""


class SourceChangedError(PipelineQueueError):
    """A source file changed while it was being copied."""


@dataclass(frozen=True, slots=True)
class IntakeCandidate:
    source_path: Path
    relative_path: Path
    received_ns: int
    size: int
    is_tag_archive: bool
    voided: bool

    @property
    def processable(self) -> bool:
        return (
            not self.is_tag_archive
            and not any(
                part.startswith(("_", "."))
                for part in self.relative_path.parts[:-1]
            )
            and self.relative_path.suffix.casefold() in PROCESSABLE_EXTENSIONS
        )


@dataclass(frozen=True, slots=True)
class IntakeSyncResult:
    mirrored: tuple[Path, ...]
    queued: tuple[Path, ...]
    already_mirrored: tuple[Path, ...]
    already_queued: tuple[Path, ...]
    already_handled: tuple[Path, ...]
    skipped_recent: tuple[Path, ...]
    ignored_for_processing: tuple[Path, ...]
    voided_for_processing: tuple[Path, ...]
    voided_moved_to_rejected: tuple[Path, ...]


def discover_intake(
    source_root: str | os.PathLike[str],
    *,
    void_registry_path: str | os.PathLike[str] | None = None,
) -> tuple[IntakeCandidate, ...]:
    """List source files deterministically, including trusted void status.

    Registry corruption raises before a candidate can be returned.  Intake
    callers must never interpret unknown void status as processable.
    """

    root = Path(source_root)
    if not root.is_dir():
        raise FileNotFoundError(f"Capture intake directory does not exist: {root}")
    voided_paths = capture_voids.voided_primary_paths(void_registry_path)

    candidates: list[IntakeCandidate] = []
    for directory, directory_names, file_names in os.walk(root):
        directory_names.sort(key=str.casefold)
        for file_name in sorted(file_names, key=str.casefold):
            source = Path(directory) / file_name
            if source.is_symlink() or not source.is_file():
                continue
            relative = source.relative_to(root)
            stat = source.stat()
            candidates.append(
                IntakeCandidate(
                    source_path=source,
                    relative_path=relative,
                    received_ns=stat.st_mtime_ns,
                    size=stat.st_size,
                    is_tag_archive=any(
                        part.casefold() == TAG_ARCHIVE_DIRNAME.casefold()
                        for part in relative.parts[:-1]
                    ),
                    voided=relative in voided_paths,
                )
            )
    candidates.sort(
        key=lambda candidate: (
            candidate.received_ns,
            str(candidate.relative_path).casefold(),
        )
    )
    return tuple(candidates)


def sync_intake_once(
    source_root: str | os.PathLike[str],
    master_root: str | os.PathLike[str],
    processing_root: str | os.PathLike[str],
    *,
    processed_root: str | os.PathLike[str],
    needs_review_root: str | os.PathLike[str],
    rejected_root: str | os.PathLike[str],
    void_registry_path: str | os.PathLike[str] | None = None,
    stable_age_seconds: float = DEFAULT_STABLE_AGE_SECONDS,
    now_ns: int | None = None,
) -> IntakeSyncResult:
    """Mirror stable capture files and queue each unhandled primary image once.

    Existing destination files are never overwritten.  If an item is already
    in ``processed``, ``needs_review``, or ``rejected``, it is not silently
    re-queued when the immutable master is scanned again.
    """

    if stable_age_seconds < 0:
        raise ValueError("stable_age_seconds cannot be negative")

    source = Path(source_root).resolve()
    master = Path(master_root).resolve()
    processing = Path(processing_root).resolve()
    terminal_roots = tuple(
        Path(root).resolve()
        for root in (processed_root, needs_review_root, rejected_root)
    )
    _assert_distinct_roots(source, master, processing, *terminal_roots)

    # Validate the complete registry before creating destinations or copying
    # anything.  Unknown void status is a hard stop, never an empty registry.
    candidates = discover_intake(
        source, void_registry_path=void_registry_path
    )

    master.mkdir(parents=True, exist_ok=True)
    processing.mkdir(parents=True, exist_ok=True)
    for root in terminal_roots:
        root.mkdir(parents=True, exist_ok=True)

    current_ns = time.time_ns() if now_ns is None else now_ns
    stable_age_ns = int(stable_age_seconds * 1_000_000_000)
    mirrored: list[Path] = []
    queued: list[Path] = []
    already_mirrored: list[Path] = []
    already_queued: list[Path] = []
    already_handled: list[Path] = []
    skipped_recent: list[Path] = []
    ignored_for_processing: list[Path] = []
    voided_for_processing: list[Path] = []
    voided_moved_to_rejected: list[Path] = []

    processed, needs_review, rejected = terminal_roots
    for candidate in candidates:
        if current_ns - candidate.received_ns < stable_age_ns:
            skipped_recent.append(candidate.relative_path)
            continue

        master_path = master / candidate.relative_path
        if _copy_additive(candidate.source_path, master_path):
            mirrored.append(candidate.relative_path)
        else:
            already_mirrored.append(candidate.relative_path)

        if not candidate.processable:
            ignored_for_processing.append(candidate.relative_path)
            continue

        if candidate.voided:
            moved = _divert_voided_item(
                candidate.relative_path,
                master_path=master_path,
                processing_root=processing,
                processed_root=processed,
                needs_review_root=needs_review,
                rejected_root=rejected,
            )
            ignored_for_processing.append(candidate.relative_path)
            voided_for_processing.append(candidate.relative_path)
            if moved:
                voided_moved_to_rejected.append(candidate.relative_path)
            continue

        lifecycle_paths = (
            processing / candidate.relative_path,
            *(root / candidate.relative_path for root in terminal_roots),
        )
        occupied = [path for path in lifecycle_paths if path.exists()]
        if len(occupied) > 1:
            locations = ", ".join(str(path) for path in occupied)
            raise StateConflictError(
                f"{candidate.relative_path} exists in multiple lifecycle roots: "
                f"{locations}"
            )
        if occupied:
            _assert_same_bytes(master_path, occupied[0])
            if occupied[0].is_relative_to(processing):
                already_queued.append(candidate.relative_path)
            else:
                already_handled.append(candidate.relative_path)
            continue

        if _copy_additive(master_path, processing / candidate.relative_path):
            queued.append(candidate.relative_path)
        else:
            already_queued.append(candidate.relative_path)

    return IntakeSyncResult(
        mirrored=tuple(mirrored),
        queued=tuple(queued),
        already_mirrored=tuple(already_mirrored),
        already_queued=tuple(already_queued),
        already_handled=tuple(already_handled),
        skipped_recent=tuple(skipped_recent),
        ignored_for_processing=tuple(ignored_for_processing),
        voided_for_processing=tuple(voided_for_processing),
        voided_moved_to_rejected=tuple(voided_moved_to_rejected),
    )


def _divert_voided_item(
    relative_path: Path,
    *,
    master_path: Path,
    processing_root: Path,
    processed_root: Path,
    needs_review_root: Path,
    rejected_root: Path,
) -> bool:
    """Keep a void out of processing, atomically rejecting queued bytes.

    Returns ``True`` only when this call moved an existing queued item.  A
    void already published as processed/review cannot be safely rewritten by
    intake and therefore raises visibly for operator intervention.
    """

    processing_path = processing_root / relative_path
    processed_path = processed_root / relative_path
    review_path = needs_review_root / relative_path
    rejected_path = rejected_root / relative_path
    lifecycle_paths = (
        processing_path,
        processed_path,
        review_path,
        rejected_path,
    )
    occupied = [path for path in lifecycle_paths if path.exists()]
    if len(occupied) > 1:
        locations = ", ".join(str(path) for path in occupied)
        raise StateConflictError(
            f"Voided {relative_path} exists in multiple lifecycle roots: {locations}"
        )
    if not occupied:
        return False

    current = occupied[0]
    _assert_same_bytes(master_path, current)
    if current == rejected_path:
        return False
    if current != processing_path:
        raise StateConflictError(
            f"Voided {relative_path} was already handled at {current}; "
            "intake cannot safely rewrite terminal history"
        )

    rejected_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(processing_path, rejected_path)
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            raise PipelineQueueError(
                "Processing and rejected roots must share a filesystem for "
                "atomic void diversion"
            ) from exc
        raise
    _remove_empty_parents(processing_path.parent, stop=processing_root)
    return True


def mark_processed(
    relative_path: str | os.PathLike[str],
    *,
    processing_root: str | os.PathLike[str],
    processed_root: str | os.PathLike[str],
) -> Path:
    return _move_lifecycle_item(relative_path, processing_root, processed_root)


def mark_needs_review(
    relative_path: str | os.PathLike[str],
    *,
    processing_root: str | os.PathLike[str],
    needs_review_root: str | os.PathLike[str],
) -> Path:
    return _move_lifecycle_item(relative_path, processing_root, needs_review_root)


def mark_rejected(
    relative_path: str | os.PathLike[str],
    *,
    processing_root: str | os.PathLike[str],
    rejected_root: str | os.PathLike[str],
) -> Path:
    return _move_lifecycle_item(relative_path, processing_root, rejected_root)


def requeue_item(
    relative_path: str | os.PathLike[str],
    *,
    status: Literal["needs_review", "rejected"],
    processing_root: str | os.PathLike[str],
    needs_review_root: str | os.PathLike[str],
    rejected_root: str | os.PathLike[str],
) -> Path:
    """Move a rejected/review source item back into the processing queue."""

    status_roots = {
        "needs_review": needs_review_root,
        "rejected": rejected_root,
    }
    try:
        source_root = status_roots[status]
    except KeyError as exc:
        raise ValueError(
            "Requeue status must be 'needs_review' or 'rejected'"
        ) from exc
    return _move_lifecycle_item(relative_path, source_root, processing_root)


def _move_lifecycle_item(
    relative_path: str | os.PathLike[str],
    source_root: str | os.PathLike[str],
    destination_root: str | os.PathLike[str],
) -> Path:
    relative = _validated_relative_path(relative_path)
    source_base = Path(source_root).resolve()
    destination_base = Path(destination_root).resolve()
    _assert_distinct_roots(source_base, destination_base)
    source = source_base / relative
    destination = destination_base / relative

    if not source.is_file():
        raise FileNotFoundError(f"Lifecycle source does not exist: {source}")
    if destination.exists():
        raise FileConflictError(f"Lifecycle destination already exists: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(source, destination)
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            raise PipelineQueueError(
                "Lifecycle roots must be on the same filesystem for an atomic move"
            ) from exc
        raise
    _remove_empty_parents(source.parent, stop=source_base)
    return destination


def _copy_additive(source: Path, destination: Path) -> bool:
    """Copy once, atomically publishing only complete bytes.

    Returns ``True`` when copied and ``False`` when an identical destination
    already exists.  A differing destination raises instead of overwriting.
    """

    if destination.exists():
        _assert_same_bytes(source, destination)
        return False

    before = source.stat()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / (
        f".{destination.name}.{uuid.uuid4().hex}.copying"
    )
    try:
        shutil.copy2(source, temporary)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (
            after.st_size,
            after.st_mtime_ns,
        ):
            raise SourceChangedError(f"Source changed during copy: {source}")
        try:
            os.link(temporary, destination)
        except FileExistsError:
            _assert_same_bytes(source, destination)
            return False
        except OSError:
            _publish_without_hardlink(temporary, destination)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _publish_without_hardlink(temporary: Path, destination: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(destination, flags)
    except FileExistsError:
        _assert_same_bytes(temporary, destination)
        return
    try:
        with os.fdopen(descriptor, "wb") as output, temporary.open("rb") as source:
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        shutil.copystat(temporary, destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _assert_same_bytes(first: Path, second: Path) -> None:
    if not first.is_file() or not second.is_file():
        raise FileConflictError(f"Expected files at {first} and {second}")
    first_stat = first.stat()
    second_stat = second.stat()
    if first_stat.st_size != second_stat.st_size:
        raise FileConflictError(
            f"Destination differs from source: {first} -> {second}"
        )
    if _sha256(first) != _sha256(second):
        raise FileConflictError(
            f"Destination differs from source: {first} -> {second}"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validated_relative_path(path: str | os.PathLike[str]) -> Path:
    relative = Path(path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"Unsafe lifecycle relative path: {path}")
    return relative


def _assert_distinct_roots(*roots: Path) -> None:
    canonical = [os.path.normcase(str(root.resolve())) for root in roots]
    if len(canonical) != len(set(canonical)):
        raise ValueError("Pipeline roots must be distinct")
    for index, root in enumerate(canonical):
        for other in canonical[index + 1 :]:
            try:
                common = os.path.commonpath((root, other))
            except ValueError:
                continue
            if common in {root, other}:
                raise ValueError("Pipeline roots cannot contain one another")


def _remove_empty_parents(start: Path, *, stop: Path) -> None:
    current = start
    while current != stop:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent
