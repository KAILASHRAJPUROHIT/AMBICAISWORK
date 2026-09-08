from __future__ import annotations

import os

import pytest

from tools import azure_flux2_guarded as guard


def _redirect_lock(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(guard, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(guard, "ACTIVE_LOCK", tmp_path / "ACTIVE_CALL.lock")


def test_stale_lock_is_reclaimed_before_new_call(monkeypatch, tmp_path) -> None:
    _redirect_lock(monkeypatch, tmp_path)
    guard.ACTIVE_LOCK.write_text("pid=99999999 utc=stale", encoding="utf-8")
    monkeypatch.setattr(guard, "_pid_is_running", lambda pid: False)

    descriptor = guard.acquire_lock()
    os.close(descriptor)
    try:
        assert f"pid={os.getpid()}" in guard.ACTIVE_LOCK.read_text(encoding="utf-8")
    finally:
        guard.ACTIVE_LOCK.unlink(missing_ok=True)


def test_live_lock_still_blocks_concurrent_call(monkeypatch, tmp_path) -> None:
    _redirect_lock(monkeypatch, tmp_path)
    guard.ACTIVE_LOCK.write_text("pid=12345 utc=live", encoding="utf-8")
    monkeypatch.setattr(guard, "_pid_is_running", lambda pid: True)

    with pytest.raises(RuntimeError, match="live PID 12345"):
        guard.acquire_lock()
