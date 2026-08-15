"""Oldest-first worker for the new processing lifecycle.

This module is inert on import. It discovers one queued primary image at a
time, derives the capture category from its tray folder, delegates generation
to an injected processor, and atomically transitions the source image into
``processed``, ``needs_review``, or ``rejected``.

Production activation is intentionally separate. The operator-approved output
policy is a centred crop for both studio and model deliverables.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import paths
import pipeline_queue


WorkerStatus = Literal["processed", "needs_review", "rejected"]
# Trailing form: "Ladies Rings 8" — the per-category scheme every capture
# folder used before the 2026-07-31 global renumbering (tray_sequence_
# migration.py). Still present on historical data (master backup, obsolete/).
_TRAY_NUMBER_TRAILING = re.compile(r"\s+\d+$")
# Leading form: "9 Ladies Rings" — the global, category-agnostic sequence
# every folder uses AFTER that renumbering (see capture_tool._tray_folder_
# name). This is the form every REAL capture folder has today; the trailing
# form above only matches historical leftovers.
_TRAY_NUMBER_LEADING = re.compile(r"^\d+\s+")

# Capture tray labels plus legacy aliases already present in the archive.
_CATEGORY_BY_FOLDER_LABEL = {
    "earrings": "earrings",
    "jhumka": "earrings",
    "ladies rings": "ladies_rings",
    "ladies ring": "ladies_rings",
    "gents rings": "gents_rings",
    "gents ring": "gents_rings",
    "ladies chains": "ladies_chains",
    "ladies chain": "ladies_chains",
    "gents chains": "gents_chains",
    "gents chain": "gents_chains",
    "ladies bracelet": "ladies_bracelet",
    "gents bracelet": "gents_bracelet",
    "ladies kada": "ladies_kada",
    "gents kada": "gents_kada",
    "locket": "locket",
    "pendant": "pendant",
    "tops": "tops",
    "wati": "wati",
    "mangalsutra (short)": "mangalsutra_short",
    "mangalsutra short": "mangalsutra_short",
    "mangalsutra (long)": "mangalsutra_long",
    "mangalsutra long": "mangalsutra_long",
    "bangles": "bangles",
    "ladies bali": "ladies_bali",
    "bali": "ladies_bali",
    "mens bali": "mens_bali",
    "men's bali": "mens_bali",
    "necklace": "necklace",
    "silver": "silver",
    "diamond": "diamond",
}


class ProcessingWorkerError(RuntimeError):
    """A queue item cannot be processed without operator attention."""


class CategoryNotReadyError(ProcessingWorkerError):
    """The folder's category is real (present in stock_category_map.py) but
    has no background/model asset configured yet — distinct from a
    genuinely unrecognised folder name. Raised so callers can choose to skip
    the item and keep waiting rather than treat it as an error."""


@dataclass(frozen=True, slots=True)
class QueueItem:
    relative_path: Path
    source_path: Path
    received_ns: int
    category: str
    tag_code: str


@dataclass(frozen=True, slots=True)
class ProcessingOutcome:
    status: WorkerStatus
    reason: str = ""
    delivery_paths: tuple[Path, ...] = ()
    unverified: bool = False


@dataclass(frozen=True, slots=True)
class WorkerResult:
    item: QueueItem
    outcome: ProcessingOutcome
    lifecycle_path: Path


def category_from_tray_folder(folder_name: str) -> str:
    """Resolve a capture tray folder in either the current global-sequence
    form (``9 Ladies Rings``) or the pre-2026-07-31 per-category form
    (``Ladies Rings 8``, still present on historical/archived data), or the
    real stock category labels (``33 Ladies Ring 22``, capture_tool.py as of
    2026-07-31 — see stock_category_map.py).

    Raises CategoryNotReadyError (not the base ProcessingWorkerError) for a
    real, recognised category that has no background/model asset yet — the
    folder name itself is fine, generation just isn't built for it. Callers
    should treat that differently from a genuinely unknown folder name.
    """
    import stock_category_map as _scm

    normalised = " ".join(folder_name.strip().casefold().split())
    for pattern in (_TRAY_NUMBER_LEADING, _TRAY_NUMBER_TRAILING):
        label = pattern.sub("", normalised).strip()
        if label in _CATEGORY_BY_FOLDER_LABEL:
            return _CATEGORY_BY_FOLDER_LABEL[label]
        cat = _scm.match_label(label)
        if cat is not None:
            if cat.existing_key:
                return cat.existing_key
            raise CategoryNotReadyError(
                f"Folder {folder_name!r} is category {cat.label!r}, "
                f"which has no background/model asset configured yet"
            )
    raise ProcessingWorkerError(
        f"Unknown capture tray category for folder {folder_name!r}"
    )


def discover_processing_queue(
    processing_root: str | os.PathLike[str] = paths.PROCESSING_DIR,
) -> tuple[QueueItem, ...]:
    """Return eligible primary images oldest-received-first."""

    root = Path(processing_root).resolve()
    if not root.is_dir():
        return ()
    items = []
    for directory, directory_names, file_names in os.walk(root):
        directory_names[:] = sorted(
            (
                name
                for name in directory_names
                if not name.startswith(("_", "."))
            ),
            key=str.casefold,
        )
        for file_name in sorted(file_names, key=str.casefold):
            path = Path(directory) / file_name
            if (
                path.is_symlink()
                or not path.is_file()
                or path.suffix.casefold()
                not in pipeline_queue.PROCESSABLE_EXTENSIONS
            ):
                continue
            relative = path.relative_to(root)
            if len(relative.parts) < 2:
                raise ProcessingWorkerError(
                    f"Queued image is not inside a tray folder: {relative}"
                )
            try:
                category = category_from_tray_folder(relative.parts[0])
            except ProcessingWorkerError as exc:
                # Either a real category with no asset yet, or a genuinely
                # unrecognised folder name — either way, skip THIS item only
                # and keep scanning the rest of the queue. A single bad/
                # not-yet-ready folder must never block every other real,
                # ready item behind it (exactly what happened before the
                # global-sequence folder-naming fix earlier today, when
                # EVERY real folder failed this check at once). The file
                # stays exactly where it is — nothing here moves or deletes
                # it — so once its category is recognised/has an asset, the
                # very next scan picks it up automatically.
                print(f"[processing_worker] skipping {relative}: {exc}")
                continue
            items.append(
                QueueItem(
                    relative_path=relative,
                    source_path=path,
                    received_ns=path.stat().st_mtime_ns,
                    category=category,
                    tag_code=path.stem,
                )
            )
    items.sort(
        key=lambda item: (
            item.received_ns,
            str(item.relative_path).casefold(),
        )
    )
    return tuple(items)


class ProcessingWorker:
    """Serial one-item lifecycle transitions around an injected processor."""

    def __init__(
        self,
        *,
        processing_root: str | os.PathLike[str] = paths.PROCESSING_DIR,
        processed_root: str | os.PathLike[str] = paths.PROCESSED_DIR,
        needs_review_root: str | os.PathLike[str] = paths.NEEDS_REVIEW_DIR,
        rejected_root: str | os.PathLike[str] = paths.REJECTED_DIR,
    ):
        self.processing_root = Path(processing_root).resolve()
        self.processed_root = Path(processed_root).resolve()
        self.needs_review_root = Path(needs_review_root).resolve()
        self.rejected_root = Path(rejected_root).resolve()
        self._lock = threading.Lock()

    def preview_next(self) -> QueueItem | None:
        queue = discover_processing_queue(self.processing_root)
        return queue[0] if queue else None

    def process_next(
        self,
        processor: Callable[[QueueItem], ProcessingOutcome],
    ) -> WorkerResult | None:
        """Process and transition one item; exceptions leave it queued."""

        with self._lock:
            item = self.preview_next()
            if item is None:
                return None
            outcome = processor(item)
            if not isinstance(outcome, ProcessingOutcome):
                raise TypeError("processor must return ProcessingOutcome")
            lifecycle_path = self._transition(item, outcome.status)
            return WorkerResult(
                item=item,
                outcome=outcome,
                lifecycle_path=lifecycle_path,
            )

    def _transition(self, item: QueueItem, status: WorkerStatus) -> Path:
        if status == "processed":
            return pipeline_queue.mark_processed(
                item.relative_path,
                processing_root=self.processing_root,
                processed_root=self.processed_root,
            )
        if status == "needs_review":
            return pipeline_queue.mark_needs_review(
                item.relative_path,
                processing_root=self.processing_root,
                needs_review_root=self.needs_review_root,
            )
        if status == "rejected":
            return pipeline_queue.mark_rejected(
                item.relative_path,
                processing_root=self.processing_root,
                rejected_root=self.rejected_root,
            )
        raise ValueError(f"Unknown processing outcome status: {status!r}")
