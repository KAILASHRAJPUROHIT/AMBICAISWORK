from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pipeline_runtime


@dataclass
class _SyncResult:
    mirrored: tuple[Path, ...] = ()
    queued: tuple[Path, ...] = ()


class _Stock:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    def refresh(self, *, as_of):
        self.calls.append(as_of)
        if self.fail:
            raise RuntimeError("workbook incomplete")
        snapshot = SimpleNamespace(
            source_path=Path("Stock/31072026.xls"),
            record_count=2795,
        )
        return SimpleNamespace(snapshot=snapshot, reloaded=True)


class _Coordinator:
    def __init__(self, *, stock_fail: bool = False, sync_fail: bool = False):
        self.stock = _Stock(fail=stock_fail)
        self.sync_fail = sync_fail
        self.sync_calls = 0

    def sync_intake(self):
        self.sync_calls += 1
        if self.sync_fail:
            raise RuntimeError("master conflict")
        return _SyncResult(
            mirrored=(Path("Locket 3/LC22_13.jpg"),),
            queued=(Path("Locket 3/LC22_13.jpg"),),
        )


def test_latest_due_stock_slot_daily_and_thursday_extra():
    ist = timezone.utc
    assert pipeline_runtime.latest_due_stock_slot(
        datetime(2026, 7, 30, 12, 0, tzinfo=ist)
    ) == datetime(2026, 7, 30, 11, 0, tzinfo=ist)
    assert pipeline_runtime.latest_due_stock_slot(
        datetime(2026, 7, 30, 13, 1, tzinfo=ist)
    ) == datetime(2026, 7, 30, 13, 0, tzinfo=ist)
    assert pipeline_runtime.latest_due_stock_slot(
        datetime(2026, 7, 31, 10, 0, tzinfo=ist)
    ) == datetime(2026, 7, 30, 13, 0, tzinfo=ist)
    assert pipeline_runtime.latest_due_stock_slot(
        datetime(2026, 7, 31, 11, 0, tzinfo=ist)
    ) == datetime(2026, 7, 31, 11, 0, tzinfo=ist)


def test_cycle_syncs_and_marks_stock_slot_once(tmp_path):
    coordinator = _Coordinator()
    runtime = pipeline_runtime.PipelineRuntime(
        coordinator, state_path=tmp_path / "state.json"
    )
    now = datetime(2026, 7, 30, 13, 5, tzinfo=timezone.utc)

    first = runtime.run_cycle(now=now)
    second = runtime.run_cycle(now=now)

    assert first.ok
    assert first.mirrored == 1
    assert first.queued == 1
    assert first.stock_refreshed
    assert second.ok
    assert not second.stock_refreshed
    assert coordinator.sync_calls == 2
    assert coordinator.stock.calls == [now.date()]
    state = runtime.read_state()
    assert state["completed_stock_slot"] == "2026-07-30T13:00:00+00:00"
    assert state["stock_records"] == 2795


def test_failed_stock_slot_is_visible_and_retried(tmp_path):
    coordinator = _Coordinator(stock_fail=True)
    runtime = pipeline_runtime.PipelineRuntime(
        coordinator, state_path=tmp_path / "state.json"
    )
    now = datetime(2026, 7, 31, 11, 5, tzinfo=timezone.utc)

    first = runtime.run_cycle(now=now)
    second = runtime.run_cycle(now=now)

    assert not first.ok
    assert first.errors == ("stock refresh failed: workbook incomplete",)
    assert not second.ok
    assert len(coordinator.stock.calls) == 2
    state = runtime.read_state()
    assert state["completed_stock_slot"] is None
    assert "workbook incomplete" in state["last_error"]


def test_cycle_attempts_stock_when_intake_sync_fails(tmp_path):
    coordinator = _Coordinator(sync_fail=True)
    runtime = pipeline_runtime.PipelineRuntime(
        coordinator, state_path=tmp_path / "state.json"
    )
    now = datetime(2026, 7, 31, 11, 5, tzinfo=timezone.utc)

    result = runtime.run_cycle(now=now)

    assert not result.ok
    assert result.stock_refreshed
    assert result.errors == ("intake sync failed: master conflict",)
    assert runtime.read_state()["completed_stock_slot"] == (
        "2026-07-31T11:00:00+00:00"
    )


def test_corrupt_state_fails_loudly(tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{broken", encoding="utf-8")
    runtime = pipeline_runtime.PipelineRuntime(_Coordinator(), state_path=state)

    try:
        runtime.read_state()
    except RuntimeError as exc:
        assert "unreadable" in str(exc)
    else:
        raise AssertionError("corrupt runtime state was silently accepted")


def test_serve_forever_emits_result_and_stops(tmp_path):
    coordinator = _Coordinator()
    runtime = pipeline_runtime.PipelineRuntime(
        coordinator, state_path=tmp_path / "state.json"
    )
    stopper = threading.Event()
    emitted = []

    def emit(message):
        emitted.append(message)
        stopper.set()

    runtime.serve_forever(
        poll_seconds=0.01,
        stop_event=stopper,
        now=lambda: datetime(2026, 7, 31, 11, 5, tzinfo=timezone.utc),
        emit=emit,
    )

    assert len(emitted) == 1
    assert '"ok": true' in emitted[0]


def test_invalid_poll_interval_is_rejected(tmp_path):
    runtime = pipeline_runtime.PipelineRuntime(
        _Coordinator(), state_path=tmp_path / "state.json"
    )

    try:
        runtime.serve_forever(poll_seconds=0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("zero poll interval was accepted")
