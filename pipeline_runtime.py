"""Explicit runtime for the additive catalogue pipeline coordinator.

Nothing starts when this module is imported.  Operators can use the CLI to
preview state, run one intake/stock cycle, or deliberately start a long-running
worker.  The live capture server is neither imported nor controlled here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

import paths
import pipeline_service
import stock_excel


STATE_VERSION = 1
DEFAULT_STATE_PATH = Path(paths.BASE) / "data" / "pipeline_runtime_state.json"
DEFAULT_POLL_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class CycleResult:
    """Outcome of one runtime cycle, including every visible failure."""

    ran_at: datetime
    stock_slot: datetime | None
    stock_refreshed: bool
    mirrored: int
    queued: int
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "ran_at": self.ran_at.isoformat(),
            "stock_slot": self.stock_slot.isoformat() if self.stock_slot else None,
            "stock_refreshed": self.stock_refreshed,
            "mirrored": self.mirrored,
            "queued": self.queued,
            "errors": list(self.errors),
        }


def latest_due_stock_slot(at: datetime) -> datetime:
    """Return the most recent required stock scan at or before ``at``.

    Looking back eight days gives a newly-started worker one catch-up scan
    without replaying every missed schedule.  Once a slot succeeds it is
    persisted, so restarts do not repeatedly parse the same workbook.
    """

    candidates: list[datetime] = []
    for offset in range(8):
        day = at.date() - timedelta(days=offset)
        for scan_time in stock_excel.scheduled_scan_times(day):
            candidate = datetime.combine(day, scan_time, tzinfo=at.tzinfo)
            if candidate <= at:
                candidates.append(candidate)
    if not candidates:
        raise RuntimeError(f"Could not find a due stock scan at {at.isoformat()}")
    return max(candidates)


class PipelineRuntime:
    """Serialise coordinator cycles and persist stock-schedule completion."""

    def __init__(
        self,
        coordinator: pipeline_service.PipelineCoordinator | None = None,
        *,
        state_path: str | os.PathLike[str] = DEFAULT_STATE_PATH,
    ):
        self.coordinator = coordinator or pipeline_service.PipelineCoordinator()
        self.state_path = Path(state_path)
        self._lock = threading.Lock()

    def read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return _empty_state()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Pipeline runtime state is unreadable: {self.state_path}: {exc}"
            ) from exc
        if not isinstance(raw, dict) or raw.get("version") != STATE_VERSION:
            raise RuntimeError(
                f"Unsupported pipeline runtime state in {self.state_path}"
            )
        return {**_empty_state(), **raw}

    def run_cycle(self, *, now: datetime | None = None) -> CycleResult:
        """Mirror stable intake files and perform any due stock refresh.

        Intake and stock failures are both attempted and returned explicitly.
        A failed stock slot is not marked complete, so the next cycle retries.
        """

        ran_at = now or datetime.now().astimezone()
        with self._lock:
            state = self.read_state()
            errors: list[str] = []
            mirrored = 0
            queued = 0

            try:
                sync = self.coordinator.sync_intake()
                mirrored = len(sync.mirrored)
                queued = len(sync.queued)
                state["last_sync_at"] = ran_at.isoformat()
            except Exception as exc:
                errors.append(f"intake sync failed: {exc}")

            stock_slot = latest_due_stock_slot(ran_at)
            stock_refreshed = False
            if state.get("completed_stock_slot") != stock_slot.isoformat():
                try:
                    refresh = self.coordinator.stock.refresh(as_of=ran_at.date())
                    stock_refreshed = refresh.reloaded
                    state["completed_stock_slot"] = stock_slot.isoformat()
                    state["last_stock_refresh_at"] = ran_at.isoformat()
                    state["stock_workbook"] = str(refresh.snapshot.source_path)
                    state["stock_records"] = refresh.snapshot.record_count
                except Exception as exc:
                    errors.append(f"stock refresh failed: {exc}")

            state["last_cycle_at"] = ran_at.isoformat()
            state["last_error"] = " | ".join(errors) if errors else None
            self._write_state(state)

        return CycleResult(
            ran_at=ran_at,
            stock_slot=stock_slot,
            stock_refreshed=stock_refreshed,
            mirrored=mirrored,
            queued=queued,
            errors=tuple(errors),
        )

    def serve_forever(
        self,
        *,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        stop_event: threading.Event | None = None,
        now: Callable[[], datetime] | None = None,
        emit: Callable[[str], None] | None = None,
    ) -> None:
        """Run cycles until stopped; failures stay visible and are retried."""

        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        stopper = stop_event or threading.Event()
        clock = now or (lambda: datetime.now().astimezone())
        output = emit or (lambda message: print(message, flush=True))
        while not stopper.is_set():
            result = self.run_cycle(now=clock())
            output(json.dumps(result.as_dict(), sort_keys=True))
            stopper.wait(poll_seconds)

    def _write_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.state_path.name}.",
            suffix=".tmp",
            dir=self.state_path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.state_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise


def _empty_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "completed_stock_slot": None,
        "last_cycle_at": None,
        "last_sync_at": None,
        "last_stock_refresh_at": None,
        "last_error": None,
        "stock_workbook": None,
        "stock_records": None,
    }


def _preview_dict(
    coordinator: pipeline_service.PipelineCoordinator,
) -> dict[str, Any]:
    preview = coordinator.preview()
    data = asdict(preview)
    data["state_conflicts"] = [str(path) for path in preview.state_conflicts]
    data["foreign_processing_files"] = [
        str(path) for path in preview.foreign_processing_files
    ]
    data["safe_to_activate"] = preview.safe_to_activate
    return data


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the additive Aradhana catalogue pipeline coordinator."
    )
    parser.add_argument(
        "--state",
        default=str(DEFAULT_STATE_PATH),
        help="runtime state JSON path",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("preview", help="read-only activation preview")
    subcommands.add_parser("status", help="show persisted runtime status")
    subcommands.add_parser("sync-once", help="run one explicit intake/stock cycle")
    daemon = subcommands.add_parser("daemon", help="run cycles until interrupted")
    daemon.add_argument(
        "--poll-seconds",
        type=float,
        default=DEFAULT_POLL_SECONDS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    runtime = PipelineRuntime(state_path=args.state)
    try:
        if args.command == "preview":
            payload = _preview_dict(runtime.coordinator)
        elif args.command == "status":
            payload = runtime.read_state()
        elif args.command == "sync-once":
            result = runtime.run_cycle()
            payload = result.as_dict()
        else:
            runtime.serve_forever(poll_seconds=args.poll_seconds)
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.command == "sync-once" and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
