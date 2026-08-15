"""Standalone coordinator for the new catalogue pipeline.

Construction and preview are read-only.  The explicit ``sync_intake`` method is
the only operation that creates/copies pipeline files; no background thread or
Flask route calls it yet.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any, Mapping

import dashboard_stats
import capture_voids
import paths
import pipeline_queue
import stock_catalog
import stock_excel


@dataclass(frozen=True, slots=True)
class PipelinePreview:
    source_files: int
    stable_primary_images: int
    stable_tag_archives: int
    recent_files: int
    files_to_mirror: int
    items_to_queue: int
    already_queued: int
    already_handled: int
    state_conflicts: tuple[Path, ...]
    foreign_processing_files: tuple[Path, ...]

    @property
    def safe_to_activate(self) -> bool:
        return not self.state_conflicts and not self.foreign_processing_files


class PipelineCoordinator:
    """Coordinate intake, stock, and dashboard state without auto-starting."""

    def __init__(
        self,
        *,
        source_capture_root: str | os.PathLike[str] = paths.LEGACY_CAPTURE_INTAKE_DIR,
        master_capture_root: str | os.PathLike[str] = paths.CAPTURE_DIR,
        processing_root: str | os.PathLike[str] = paths.PROCESSING_DIR,
        processed_root: str | os.PathLike[str] = paths.PROCESSED_DIR,
        needs_review_root: str | os.PathLike[str] = paths.NEEDS_REVIEW_DIR,
        rejected_root: str | os.PathLike[str] = paths.REJECTED_DIR,
        void_registry_path: str | os.PathLike[str] | None = None,
        stock_dir: str | os.PathLike[str] = stock_excel.STOCK_DIR,
    ):
        self.source_capture_root = Path(source_capture_root)
        self.master_capture_root = Path(master_capture_root)
        self.processing_root = Path(processing_root)
        self.processed_root = Path(processed_root)
        self.needs_review_root = Path(needs_review_root)
        self.rejected_root = Path(rejected_root)
        self.void_registry_path = Path(
            void_registry_path or capture_voids.configured_void_registry_path()
        )
        self.stock = stock_catalog.StockCatalogCache(stock_dir)
        self._lock = threading.RLock()
        self.last_sync: pipeline_queue.IntakeSyncResult | None = None
        self.last_sync_at: datetime | None = None
        self.last_sync_error: str | None = None

    def preview(
        self,
        *,
        stable_age_seconds: float = pipeline_queue.DEFAULT_STABLE_AGE_SECONDS,
        now_ns: int | None = None,
    ) -> PipelinePreview:
        if stable_age_seconds < 0:
            raise ValueError("stable_age_seconds cannot be negative")
        current_ns = time.time_ns() if now_ns is None else now_ns
        stable_age_ns = int(stable_age_seconds * 1_000_000_000)
        candidates = pipeline_queue.discover_intake(
            self.source_capture_root,
            void_registry_path=self.void_registry_path,
        )
        stable = [
            candidate
            for candidate in candidates
            if current_ns - candidate.received_ns >= stable_age_ns
        ]
        recent = len(candidates) - len(stable)
        files_to_mirror = sum(
            not (self.master_capture_root / candidate.relative_path).exists()
            for candidate in stable
        )

        primary = [candidate for candidate in stable if candidate.processable]
        active_primary = [candidate for candidate in primary if not candidate.voided]
        primary_relatives = {candidate.relative_path for candidate in primary}
        state_conflicts: list[Path] = []
        items_to_queue = 0
        already_queued = 0
        already_handled = 0
        terminal_roots = (
            self.processed_root,
            self.needs_review_root,
            self.rejected_root,
        )
        for candidate in active_primary:
            lifecycle = (
                self.processing_root / candidate.relative_path,
                *(root / candidate.relative_path for root in terminal_roots),
            )
            occupied = [path for path in lifecycle if path.exists()]
            if len(occupied) > 1:
                state_conflicts.append(candidate.relative_path)
            elif not occupied:
                items_to_queue += 1
            elif occupied[0].is_relative_to(self.processing_root):
                already_queued += 1
            else:
                already_handled += 1

        foreign_processing = tuple(
            sorted(
                (
                    path.relative_to(self.processing_root)
                    for path in _primary_images_if_present(self.processing_root)
                    if path.relative_to(self.processing_root) not in primary_relatives
                ),
                key=lambda relative: str(relative).casefold(),
            )
        )
        return PipelinePreview(
            source_files=len(candidates),
            stable_primary_images=len(primary),
            stable_tag_archives=sum(
                candidate.is_tag_archive for candidate in stable
            ),
            recent_files=recent,
            files_to_mirror=files_to_mirror,
            items_to_queue=items_to_queue,
            already_queued=already_queued,
            already_handled=already_handled,
            state_conflicts=tuple(state_conflicts),
            foreign_processing_files=foreign_processing,
        )

    def sync_intake(self) -> pipeline_queue.IntakeSyncResult:
        """Run one explicit additive sync; never called automatically."""

        try:
            result = pipeline_queue.sync_intake_once(
                self.source_capture_root,
                self.master_capture_root,
                self.processing_root,
                processed_root=self.processed_root,
                needs_review_root=self.needs_review_root,
                rejected_root=self.rejected_root,
                void_registry_path=self.void_registry_path,
            )
        except Exception as exc:
            with self._lock:
                self.last_sync_error = str(exc)
            raise
        with self._lock:
            self.last_sync = result
            self.last_sync_at = datetime.now()
            self.last_sync_error = None
        return result

    def refresh_stock(self):
        return self.stock.refresh()

    def dashboard(
        self,
        *,
        now: datetime | None = None,
        timezone: tzinfo | None = None,
        external_health: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dashboard_stats.DashboardStats:
        return dashboard_stats.collect_dashboard_stats(
            # Live captured counts come from the production intake.  The
            # immutable mirror can legitimately lag behind the phone-facing
            # capture tree and may use a different archival layout; counting
            # it made the dashboard stale or zero while capture_intake was
            # healthy and populated.
            capture_root=self.source_capture_root,
            processing_root=self.processing_root,
            processed_root=self.processed_root,
            needs_review_root=self.needs_review_root,
            rejected_root=self.rejected_root,
            stock_snapshot=self.stock.snapshot,
            stock_tag_count=self.stock.inventory_tag_count,
            now=now,
            timezone=timezone,
            external_health=external_health,
        )


def _primary_images_if_present(root: Path):
    if not root.is_dir():
        return
    for directory, directory_names, file_names in os.walk(root):
        directory_names[:] = [
            name
            for name in directory_names
            if name.casefold() != pipeline_queue.TAG_ARCHIVE_DIRNAME.casefold()
            and not name.startswith(".")
        ]
        for file_name in file_names:
            path = Path(directory) / file_name
            if (
                path.suffix.casefold() in pipeline_queue.PROCESSABLE_EXTENSIONS
                and path.is_file()
                and not path.is_symlink()
            ):
                yield path
