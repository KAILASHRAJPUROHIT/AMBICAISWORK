from __future__ import annotations

from pathlib import Path

import pytest

import app


def _model_file(tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"model")
    return path


def test_matching_manual_model_reference_is_used(tmp_path, monkeypatch):
    model = _model_file(tmp_path, "female/legacy/ear_front.jpg")
    monkeypatch.setattr(app, "MODELS_DIR", str(tmp_path))

    resolved, variant = app._resolve_model_ref(
        "earrings", {"modelPath": "female/legacy/ear_front.jpg"}
    )

    assert resolved == str(model)
    assert variant is None


def test_mismatched_manual_pose_fails_loudly_without_override(
    tmp_path, monkeypatch
):
    _model_file(tmp_path, "female/legacy/feet_standing.jpg")
    monkeypatch.setattr(app, "MODELS_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="MODEL_POSE_MISMATCH"):
        app._resolve_model_ref(
            "earrings", {"modelPath": "female/legacy/feet_standing.jpg"}
        )


def test_explicit_manual_pose_override_uses_pinned_reference(
    tmp_path, monkeypatch
):
    model = _model_file(tmp_path, "female/legacy/feet_standing.jpg")
    monkeypatch.setattr(app, "MODELS_DIR", str(tmp_path))

    resolved, variant = app._resolve_model_ref(
        "earrings",
        {
            "modelPath": "female/legacy/feet_standing.jpg",
            "allowPoseOverride": True,
        },
    )

    assert resolved == str(model)
    assert variant is None


def test_missing_pinned_reference_never_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MODELS_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="MODEL_REFERENCE_NOT_FOUND"):
        app._resolve_model_ref(
            "earrings", {"modelPath": "female/legacy/missing.jpg"}
        )


def test_pinned_reference_cannot_escape_model_root(tmp_path, monkeypatch):
    outside = tmp_path.parent / "outside.jpg"
    outside.write_bytes(b"outside")
    monkeypatch.setattr(app, "MODELS_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="MODEL_REFERENCE_INVALID"):
        app._resolve_model_ref(
            "earrings", {"modelPath": "../outside.jpg", "allowPoseOverride": True}
        )


def test_pinned_reference_on_another_windows_drive_is_invalid(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(app, "MODELS_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="MODEL_REFERENCE_INVALID"):
        app._resolve_model_ref(
            "earrings",
            {"modelPath": r"Z:\outside.jpg", "allowPoseOverride": True},
        )


def test_pose_override_survives_per_pair_model_cycling():
    original = {
        "enabled": True,
        "modelPath": "female/ear_front.jpg",
        "modelPaths": [
            "female/ear_front.jpg",
            "female/feet_standing.jpg",
        ],
        "allowPoseOverride": True,
    }

    second = app._cycled_model_cfg(original, 1)

    assert second["modelPath"] == "female/feet_standing.jpg"
    assert second["allowPoseOverride"] is True
    assert original["modelPath"] == "female/ear_front.jpg"


def test_model_images_default_filters_and_override_lists_all(
    tmp_path, monkeypatch
):
    _model_file(tmp_path, "female/legacy/ear_front.jpg")
    _model_file(tmp_path, "female/legacy/feet_standing.jpg")
    _model_file(tmp_path, "female/legacy/profile.jpg")
    monkeypatch.setattr(app, "MODELS_DIR", str(tmp_path))

    with app.app.test_request_context(
        "/api/model_images?category=earrings&group=female&style=legacy"
    ):
        safe_payload = app.api_model_images().get_json()
    with app.app.test_request_context(
        "/api/model_images?category=earrings&group=female&style=legacy"
        "&include_all_poses=1"
    ):
        all_payload = app.api_model_images().get_json()

    safe_names = {Path(image["path"]).name for image in safe_payload["images"]}
    all_names = {Path(image["path"]).name for image in all_payload["images"]}
    assert safe_payload["expected_zone"] == "face"
    assert safe_names == {"ear_front.jpg", "profile.jpg"}
    assert all_payload["expected_zone"] == "face"
    assert all_names == {"ear_front.jpg", "feet_standing.jpg", "profile.jpg"}
