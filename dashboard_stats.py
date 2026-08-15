"""Read-only backend metrics for the production dashboard."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any, Mapping

from pipeline_queue import PROCESSABLE_EXTENSIONS, TAG_ARCHIVE_DIRNAME
from stock_excel import StockSnapshot


@dataclass(frozen=True, slots=True)
class SegmentHealth:
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class DashboardStats:
    captured_today: int
    captured_total: int
    stock_tags: int
    stock_pieces: int
    processing_available: int
    processed_total: int
    needs_review_total: int
    rejected_total: int
    last_captured_at: datetime | None
    last_processed_at: datetime | None
    health: dict[str, SegmentHealth]

    @property
    def overall_ok(self) -> bool:
        return all(segment.ok for segment in self.health.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall_ok": self.overall_ok,
            "captured_today": self.captured_today,
            "captured_total": self.captured_total,
            "stock_tags": self.stock_tags,
            "stock_pieces": self.stock_pieces,
            "processing_available": self.processing_available,
            "processed_total": self.processed_total,
            "needs_review_total": self.needs_review_total,
            "rejected_total": self.rejected_total,
            "last_captured_at": (
                self.last_captured_at.isoformat() if self.last_captured_at else None
            ),
            "last_processed_at": (
                self.last_processed_at.isoformat() if self.last_processed_at else None
            ),
            "health": {
                name: {"ok": segment.ok, "detail": segment.detail}
                for name, segment in self.health.items()
            },
        }


@dataclass(frozen=True, slots=True)
class _DirectoryMetrics:
    count: int
    latest_mtime: float | None
    exists: bool


def collect_dashboard_stats(
    *,
    capture_root: str | os.PathLike[str],
    processing_root: str | os.PathLike[str],
    processed_root: str | os.PathLike[str],
    needs_review_root: str | os.PathLike[str],
    rejected_root: str | os.PathLike[str],
    stock_snapshot: StockSnapshot | None,
    stock_tag_count: int | None = None,
    now: datetime | None = None,
    timezone: tzinfo | None = None,
    external_health: Mapping[str, Mapping[str, Any]] | None = None,
) -> DashboardStats:
    """Collect filesystem and stock counts without creating or probing files."""

    current = now or datetime.now(tz=timezone)
    capture = _directory_metrics(capture_root)
    processing = _directory_metrics(processing_root)
    processed = _directory_metrics(processed_root)
    needs_review = _directory_metrics(needs_review_root)
    rejected = _directory_metrics(rejected_root)

    captured_today = _count_for_date(capture_root, current.date(), timezone)
    health = {
        "capture": _directory_health(capture_root, capture),
        "processing": _directory_health(processing_root, processing),
        "processed": _directory_health(processed_root, processed),
        "needs_review": _directory_health(needs_review_root, needs_review),
        "rejected": _directory_health(rejected_root, rejected),
        "stock": SegmentHealth(
            stock_snapshot is not None,
            (
                f"{stock_snapshot.record_count} tags from "
                f"{stock_snapshot.source_path.name}"
                if stock_snapshot is not None
                else "no validated stock workbook loaded"
            ),
        ),
    }
    for name, check in (external_health or {}).items():
        health[name] = SegmentHealth(
            bool(check.get("ok")),
            str(check.get("detail", "")),
        )

    return DashboardStats(
        captured_today=captured_today,
        captured_total=capture.count,
        stock_tags=(
            stock_tag_count
            if stock_tag_count is not None
            else stock_snapshot.record_count if stock_snapshot else 0
        ),
        stock_pieces=stock_snapshot.total_pieces if stock_snapshot else 0,
        processing_available=processing.count,
        processed_total=processed.count,
        needs_review_total=needs_review.count,
        rejected_total=rejected.count,
        last_captured_at=_as_datetime(capture.latest_mtime, timezone),
        last_processed_at=_as_datetime(processed.latest_mtime, timezone),
        health=health,
    )


def _directory_metrics(root: str | os.PathLike[str]) -> _DirectoryMetrics:
    path = Path(root)
    if not path.is_dir():
        return _DirectoryMetrics(0, None, False)
    mtimes = [item.stat().st_mtime for item in _iter_primary_images(path)]
    return _DirectoryMetrics(
        count=len(mtimes),
        latest_mtime=max(mtimes) if mtimes else None,
        exists=True,
    )


def _count_for_date(
    root: str | os.PathLike[str],
    target_date,
    timezone: tzinfo | None,
) -> int:
    path = Path(root)
    if not path.is_dir():
        return 0
    return sum(
        1
        for item in _iter_primary_images(path)
        if _as_datetime(item.stat().st_mtime, timezone).date() == target_date
    )


def _iter_primary_images(root: Path):
    for directory, directory_names, file_names in os.walk(root):
        directory_names[:] = [
            name
            for name in directory_names
            if name.casefold() != TAG_ARCHIVE_DIRNAME.casefold()
            and not name.startswith(".")
        ]
        for file_name in file_names:
            path = Path(directory) / file_name
            if (
                not file_name.startswith(".")
                and path.suffix.casefold() in PROCESSABLE_EXTENSIONS
                and path.is_file()
                and not path.is_symlink()
            ):
                yield path


def _directory_health(
    root: str | os.PathLike[str],
    metrics: _DirectoryMetrics,
) -> SegmentHealth:
    if not metrics.exists:
        return SegmentHealth(False, f"missing directory: {Path(root)}")
    return SegmentHealth(True, f"{metrics.count} processable image(s)")


def _as_datetime(timestamp: float | None, timezone: tzinfo | None) -> datetime | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone)
