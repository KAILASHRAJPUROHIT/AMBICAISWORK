"""Tests for the standalone target-directory configuration."""

import importlib
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import paths


ENVIRONMENT_VARIABLES = {
    "AJ_CAPTURE_DIR": "capture",
    "AJ_PROCESSING_DIR": "processing",
    "AJ_PROCESSED_DIR": "processed",
    "AJ_OUTPUT_DIR": "output",
    "AJ_NEEDS_REVIEW_DIR": "needs_review",
    "AJ_REJECTED_DIR": "rejected",
    "AJ_BACKGROUNDS_DIR": "backgrounds",
    "AJ_MODELS_DIR": "models",
}


def _reload_with_isolated_roots(monkeypatch, tmp_path):
    for environment_variable, directory_name in ENVIRONMENT_VARIABLES.items():
        monkeypatch.setenv(
            environment_variable,
            str(tmp_path / "target" / directory_name),
        )
    return importlib.reload(paths)


def test_roots_are_distinct(monkeypatch):
    with monkeypatch.context() as isolated_environment:
        for environment_variable in ENVIRONMENT_VARIABLES:
            isolated_environment.delenv(environment_variable, raising=False)
        configured = importlib.reload(paths)
        canonical_roots = {
            os.path.normcase(os.path.realpath(root)) for root in configured.ROOTS
        }
        assert len(configured.ROOTS) == 8
        assert len(canonical_roots) == 8
    importlib.reload(paths)


def test_environment_overrides_all_roots(monkeypatch, tmp_path):
    with monkeypatch.context() as isolated_environment:
        configured = _reload_with_isolated_roots(isolated_environment, tmp_path)
        expected = {
            name: os.path.normpath(str(tmp_path / "target" / name))
            for name in ENVIRONMENT_VARIABLES.values()
        }
        assert configured.ROOTS_BY_NAME == expected
    importlib.reload(paths)


def test_ensure_dirs_is_idempotent(monkeypatch, tmp_path):
    with monkeypatch.context() as isolated_environment:
        configured = _reload_with_isolated_roots(isolated_environment, tmp_path)
        configured.ensure_dirs()
        configured.ensure_dirs()
        assert all(os.path.isdir(root) for root in configured.ROOTS)
    importlib.reload(paths)


def test_ensure_dirs_does_not_touch_capture_intake(monkeypatch, tmp_path):
    legacy_capture = tmp_path / "capture_intake"
    sentinel = legacy_capture / "open tray" / "captured.jpg"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"untouched master capture")

    with monkeypatch.context() as isolated_environment:
        configured = _reload_with_isolated_roots(isolated_environment, tmp_path)
        before = {
            path.relative_to(legacy_capture): path.read_bytes()
            for path in legacy_capture.rglob("*")
            if path.is_file()
        }
        configured.ensure_dirs()
        after = {
            path.relative_to(legacy_capture): path.read_bytes()
            for path in legacy_capture.rglob("*")
            if path.is_file()
        }
        assert after == before
        assert list(legacy_capture.rglob("*")) == [
            legacy_capture / "open tray",
            sentinel,
        ]
    importlib.reload(paths)


def test_ensure_dirs_rejects_a_root_inside_capture_intake(monkeypatch, tmp_path):
    legacy_capture = tmp_path / "capture_intake"
    legacy_capture.mkdir()
    unsafe_root = legacy_capture / "must-not-be-created"

    monkeypatch.setattr(paths, "LEGACY_CAPTURE_INTAKE_DIR", str(legacy_capture))

    try:
        paths.ensure_dirs([str(unsafe_root)])
    except ValueError as exc:
        assert "capture_intake" in str(exc)
    else:
        raise AssertionError("ensure_dirs accepted a root inside capture_intake")

    assert not unsafe_root.exists()


def test_current_to_target_mapping_is_documentation_only():
    assert paths.CURRENT_TO_TARGET["capture_intake"] == "capture"
    assert paths.CURRENT_TO_TARGET["output_aradhana"] == "output"
    assert paths.CURRENT_TO_TARGET["Reject"] == "rejected"
