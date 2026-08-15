from __future__ import annotations

from types import SimpleNamespace

import app
import processed_state


def test_processed_reset_preview_parses_selected_tags(monkeypatch):
    captured = {}

    def preview(tags):
        captured["tags"] = tags
        return SimpleNamespace(as_dict=lambda: {
            "tags": list(tags), "processed_files": [], "processed_file_count": 0,
            "progress_records": 1, "catalogue_records": 1,
            "conflicts": [], "can_reset": True,
        })

    monkeypatch.setattr(processed_state, "preview_reset", preview)
    with app.app.test_request_context(
        "/api/pipeline/processed_reset/preview?scope=tags&tags=LR22_7,LR22_9-LR22_10"
    ):
        response = app.api_processed_reset_preview()
        payload = response.get_json()

    assert payload["ok"] is True
    assert captured["tags"] == ("LR22_7", "LR22_9", "LR22_10")


def test_processed_reset_requires_exact_confirmation(monkeypatch):
    monkeypatch.setattr(app, "_processed_reset_blocked", lambda: False)
    with app.app.test_request_context(
        "/api/pipeline/processed_reset",
        method="POST",
        json={"scope": "all", "confirmation": "yes"},
    ):
        response, status = app.api_processed_reset()
    assert status == 400
    assert "RESET ALL PROCESSED" in response.get_json()["error"]


def test_processed_reset_is_blocked_while_processing_runs(monkeypatch):
    monkeypatch.setattr(app, "_processed_reset_blocked", lambda: True)
    with app.app.test_request_context(
        "/api/pipeline/processed_reset",
        method="POST",
        json={"scope": "all", "confirmation": "RESET ALL PROCESSED"},
    ):
        response, status = app.api_processed_reset()
    assert status == 409
    assert "Stop Manual/Auto" in response.get_json()["error"]


def test_processed_reset_applies_selected_tags(monkeypatch):
    captured = {}
    monkeypatch.setattr(app, "_processed_reset_blocked", lambda: False)

    def apply(tags):
        captured["tags"] = tags
        return {
            "tags": list(tags), "processed_files": [], "processed_file_count": 0,
            "progress_records": 1, "catalogue_records": 1, "conflicts": [],
            "can_reset": True, "moved_to_processing": 0, "backup": "backup/path",
        }

    monkeypatch.setattr(processed_state, "apply_reset", apply)
    with app.app.test_request_context(
        "/api/pipeline/processed_reset",
        method="POST",
        json={
            "scope": "tags", "tags": "LR22_7 LR22_9",
            "confirmation": "RESET SELECTED PROCESSED",
        },
    ):
        payload = app.api_processed_reset().get_json()

    assert payload["ok"] is True
    assert captured["tags"] == ("LR22_7", "LR22_9")
