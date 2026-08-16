"""
Tests for single_instance.py -- exercises the lock file's own logic
(read/write/PID-matching) without spawning or killing real processes.
"""
import os

import psutil
import pytest

import single_instance


@pytest.fixture(autouse=True)
def _isolated_lock_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(single_instance, "LOCK_DIR", str(tmp_path))
    yield


def test_first_call_writes_own_pid():
    single_instance.enforce_single_instance("testsvc")
    path = single_instance._lock_path("testsvc")
    assert os.path.isfile(path)
    assert int(open(path).read().strip()) == os.getpid()


def test_stale_dead_pid_is_overwritten():
    path = single_instance._lock_path("testsvc")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # A PID that (almost certainly) no longer exists.
    dead_pid = 999999
    while psutil.pid_exists(dead_pid) and dead_pid > 1:
        dead_pid -= 1
    with open(path, "w") as f:
        f.write(str(dead_pid))
    single_instance.enforce_single_instance("testsvc")
    assert int(open(path).read().strip()) == os.getpid()


def test_live_unrelated_process_is_not_killed():
    # The current test-runner process is alive but its cmdline does NOT
    # mention "testsvc" -- enforce_single_instance must not touch it, only
    # overwrite the lock file with our own PID.
    path = single_instance._lock_path("testsvc")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    other_pid = os.getppid()
    with open(path, "w") as f:
        f.write(str(other_pid))
    single_instance.enforce_single_instance("testsvc")
    assert psutil.pid_exists(other_pid)
    assert int(open(path).read().strip()) == os.getpid()
