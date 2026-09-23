"""Safe operator-facing facade for lifecycle requeue operations.

Listing and previewing are read-only.  A requeue requires the exact token from
the current preview, so a file changed after confirmation cannot be moved under
a stale operator decision.  The actual transition delegates to
``pipeline_queue.requeue_item`` and therefore remains an atomic, no-overwrite
rename on the same filesystem.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pipeline_queue


ALLOWED_STATUSES = frozenset({"needs_review", "rejected"})


class RequeueValidationError(ValueError):
    """A request does not satisfy the lifecycle API contract."""


class RequeueSourceNotFound(FileNotFoundError):
    """The requested source item is absent from its lifecycle root."""


class RequeueConflictError(RuntimeError):
    """The processing destination is occupied or otherwise unsafe."""


@dataclass(frozen=True, slots=True)
class RequeueItem:
    status: str
    relative_path: str
    name: str
    size: int
    modified_at: str
    modified_ns: int
    destination_exists: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "relative_path": self.relative_path,
            "name": self.name,
            "size": self.size,
            "modified_at": self.modified_at,
            "destination_exists": self.destination_exists,
        }


class LifecycleRequeueService:
    def __init__(
        self,
        *,
        processing_root: str | os.PathLike[str],
        needs_review_root: str | os.PathLike[str],
        rejected_root: str | os.PathLike[str],
    ):
        self.processing_root = Path(processing_root).resolve()
        self.status_roots = {
            "needs_review": Path(needs_review_root).resolve(),
            "rejected": Path(rejected_root).resolve(),
        }
        _validate_distinct_roots(self.processing_root, *self.status_roots.values())

    def list_items(self, status: str) -> tuple[RequeueItem, ...]:
        """Return eligible source items without creating or modifying paths."""

        source_root = self._status_root(status)
        if not source_root.is_dir():
            return ()
        items: list[RequeueItem] = []
        for candidate in source_root.rglob("*"):
            if (
                candidate.is_symlink()
                or not candidate.is_file()
                or candidate.suffix.casefold() not in pipeline_queue.PROCESSABLE_EXTENSIONS
            ):
                continue
            relative = candidate.relative_to(source_root)
            if any(part.startswith((".", "_")) for part in relative.parts):
                continue
            try:
                items.append(self._inspect(status, relative))
            except RequeueSourceNotFound:
                # A worker may complete a lifecycle move during a read-only
                # listing.  Omitting that now-absent item is the safe result.
                continue
        items.sort(key=lambda item: (item.modified_ns, item.relative_path.casefold()))
        return tuple(items)

    def preview(self, status: str, relative_path: str) -> dict[str, object]:
        item = self._inspect(status, _validated_relative_path(relative_path))
        payload = item.as_dict()
        payload.update(
            {
                "can_requeue": not item.destination_exists,
                "confirmation_token": _confirmation_token(item),
                "destination": {
                    "status": "processing",
                    "relative_path": item.relative_path,
                },
            }
        )
        if item.destination_exists:
            payload["conflict"] = "processing destination already exists"
        return payload

    def requeue(
        self,
        status: str,
        relative_path: str,
        confirmation_token: str,
    ) -> dict[str, object]:
        relative = _validated_relative_path(relative_path)
        item = self._inspect(status, relative)
        if not isinstance(confirmation_token, str) or confirmation_token != _confirmation_token(item):
            raise RequeueValidationError(
                "confirmation_token must exactly match the current preview"
            )
        if item.destination_exists:
            raise RequeueConflictError("Processing destination already exists")
        try:
            moved_destination = pipeline_queue.requeue_item(
                relative,
                status=status,
                processing_root=self.processing_root,
                needs_review_root=self.status_roots["needs_review"],
                rejected_root=self.status_roots["rejected"],
            )
        except FileNotFoundError as exc:
            raise RequeueSourceNotFound(str(exc)) from exc
        except (pipeline_queue.FileConflictError, pipeline_queue.StateConflictError) as exc:
            raise RequeueConflictError(str(exc)) from exc
        except pipeline_queue.PipelineQueueError as exc:
            raise RequeueConflictError(str(exc)) from exc

        destination = _confined_candidate(self.processing_root, relative)
        if Path(moved_destination).resolve() != destination:
            raise RequeueConflictError("Requeue returned an unsafe destination")
        stat = destination.stat()
        return {
            "ok": True,
            "source_status": status,
            "destination": {
                "status": "processing",
                "relative_path": relative.as_posix(),
                "name": destination.name,
                "size": stat.st_size,
                "modified_at": _iso_timestamp(stat.st_mtime),
            },
        }

    def _status_root(self, status: str) -> Path:
        if not isinstance(status, str) or status not in ALLOWED_STATUSES:
            raise RequeueValidationError(
                "status must be exactly 'needs_review' or 'rejected'"
            )
        return self.status_roots[status]

    def _inspect(self, status: str, relative: Path) -> RequeueItem:
        source_root = self._status_root(status)
        source = _confined_candidate(source_root, relative)
        destination = _confined_candidate(self.processing_root, relative)
        if source.is_symlink() or not source.is_file():
            raise RequeueSourceNotFound(
                f"Lifecycle source does not exist: {relative.as_posix()}"
            )
        stat = source.stat()
        return RequeueItem(
            status=status,
            relative_path=relative.as_posix(),
            name=source.name,
            size=stat.st_size,
            modified_at=_iso_timestamp(stat.st_mtime),
            modified_ns=stat.st_mtime_ns,
            destination_exists=destination.exists(),
        )


def _validated_relative_path(value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise RequeueValidationError("path must be a non-empty relative path")
    if value != value.strip():
        raise RequeueValidationError("path must not contain surrounding whitespace")
    relative = Path(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RequeueValidationError("path must be relative and root-confined")
    return relative


def _confined_candidate(root: Path, relative: Path) -> Path:
    candidate = root / relative
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise RequeueValidationError("path escapes its lifecycle root")
    return resolved


def _confirmation_token(item: RequeueItem) -> str:
    return (
        f"REQUEUE::{item.status}::{item.relative_path}::"
        f"{item.size}::{item.modified_ns}"
    )


def _iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _validate_distinct_roots(*roots: Path) -> None:
    canonical = [os.path.normcase(str(root)) for root in roots]
    if len(canonical) != len(set(canonical)):
        raise RequeueValidationError("Lifecycle roots must be distinct")
    for index, root in enumerate(canonical):
        for other in canonical[index + 1 :]:
            if os.path.commonpath((root, other)) in {root, other}:
                raise RequeueValidationError("Lifecycle roots cannot contain one another")
