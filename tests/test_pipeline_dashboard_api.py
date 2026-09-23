from __future__ import annotations

from types import SimpleNamespace

import app


class _Stats:
    def __init__(self, payload):
        self.payload = payload

    def as_dict(self):
        return dict(self.payload)


class _Coordinator:
    def __init__(self, *, refresh_error=None):
        self.refresh_error = refresh_error
        self.dashboard_kwargs = None
        self.refresh_calls = 0

    def refresh_stock(self):
        self.refresh_calls += 1
        if self.refresh_error:
            raise self.refresh_error

    def dashboard(self, **kwargs):
        self.dashboard_kwargs = kwargs
        return _Stats(
            {
                "overall_ok": True,
                "captured_today": 6,
                "captured_total": 318,
                "stock_tags": 2795,
                "stock_pieces": 2898,
                "processing_available": 318,
                "processed_total": 0,
                "needs_review_total": 0,
                "rejected_total": 0,
                "last_captured_at": "2026-07-31T13:57:40+05:30",
                "last_processed_at": None,
                "health": kwargs["external_health"],
            }
        )


def test_pipeline_dashboard_returns_fixed_contract(monkeypatch):
    coordinator = _Coordinator()
    monkeypatch.setattr(app, "_get_pipeline_coordinator", lambda: coordinator)
    monkeypatch.setattr(
        app,
        "_cached_pipeline_system_health",
        lambda: {"capture_server": {"ok": True, "detail": "listening"}},
    )

    with app.app.app_context():
        response = app.api_pipeline_dashboard()
        payload = response.get_json()

    assert payload["captured_today"] == 6
    assert payload["processing_available"] == 318
    assert payload["stock_tags"] == 2795
    assert payload["health"]["capture_server"]["ok"]
    assert payload["stock_updated_at"] is None
    assert payload["stock_source"] is None
    assert coordinator.refresh_calls == 1
    assert coordinator.dashboard_kwargs["now"].tzinfo is not None
    assert coordinator.dashboard_kwargs["timezone"] is not None


def test_stock_refresh_failure_is_visible_without_zeroing_counts(monkeypatch):
    coordinator = _Coordinator(refresh_error=RuntimeError("new workbook incomplete"))
    monkeypatch.setattr(app, "_get_pipeline_coordinator", lambda: coordinator)
    monkeypatch.setattr(
        app,
        "_cached_pipeline_system_health",
        lambda: {"disk": {"ok": True, "detail": "writable"}},
    )

    with app.app.app_context():
        payload = app.api_pipeline_dashboard().get_json()

    assert payload["stock_tags"] == 2795
    assert not payload["health"]["stock"]["ok"]
    assert "new workbook incomplete" in payload["health"]["stock"]["detail"]
    assert payload["health"]["disk"]["ok"]


def test_stock_metadata_warning_is_healthy_and_reports_workbook_time(monkeypatch, tmp_path):
    workbook = tmp_path / "01082026.xls"
    workbook.write_bytes(b"stock")
    inventory = SimpleNamespace(
        record_count=2814,
        source_path=workbook,
    )
    refresh = SimpleNamespace(
        inventory=inventory,
        warning="39 current tag(s) await rich metadata",
    )
    coordinator = _Coordinator()
    coordinator.refresh_stock = lambda: refresh
    monkeypatch.setattr(app, "_get_pipeline_coordinator", lambda: coordinator)
    monkeypatch.setattr(app, "_cached_pipeline_system_health", lambda: {})

    with app.app.app_context():
        payload = app.api_pipeline_dashboard().get_json()

    assert payload["health"]["stock"]["ok"] is True
    assert "39 current tag(s)" in payload["health"]["stock"]["detail"]
    assert payload["stock_source"] == "01082026.xls"
    assert payload["stock_updated_at"] is not None


def test_latest_capture_record_returns_tagged_jewellery_preview(monkeypatch, tmp_path):
    import capture_tool

    tray = tmp_path / "40 LOCKET 22"
    tray.mkdir()
    image = tray / "LC22_156.jpg"
    image.write_bytes(b"preview")
    monkeypatch.setattr(capture_tool, "CAPTURE_ROOT", str(tmp_path))
    monkeypatch.setattr(capture_tool, "_load_dedup", lambda: {
        "LC22_156": {
            "folder": "40 LOCKET 22",
            "filename": "LC22_156.jpg",
            "ts": 1785600000.0,
        }
    })

    latest = app._latest_capture_record()

    assert latest["tag"] == "LC22_156"
    assert latest["relative_path"] == "40 LOCKET 22/LC22_156.jpg"
    assert latest["preview_url"].startswith("/api/pipeline/latest_capture_preview?v=")


def test_live_snapshot_coalesces_dashboard_category_and_capture(monkeypatch):
    calls = {"dashboard": 0, "categories": 0, "capture": 0}

    def response(name, payload):
        def build():
            calls[name] += 1
            return app.jsonify(payload)
        return build

    monkeypatch.setattr(
        app,
        "api_pipeline_dashboard",
        response("dashboard", {"captured_total": 772}),
    )
    monkeypatch.setattr(
        app,
        "api_pipeline_category_breakdown",
        response("categories", {"categories": [{"label": "TOPS 22", "captured": 203}]}),
    )
    monkeypatch.setattr(
        app,
        "api_capture_live_status",
        response("capture", {"reachable": True, "active_trays": {"tops_22": "56 TOPS 22"}}),
    )
    monkeypatch.setattr(
        app,
        "_PIPELINE_LIVE_CACHE",
        {"expires_at": 0.0, "payload": None, "signature": None, "generation": 0},
    )
    monkeypatch.setattr(app, "_pipeline_live_signature", lambda: ("stable",))

    with app.app.app_context():
        first = app.api_pipeline_live_snapshot().get_json()
        second = app.api_pipeline_live_snapshot().get_json()

    assert first == second
    assert first["dashboard"]["captured_total"] == 772
    assert first["categories"][0]["label"] == "TOPS 22"
    assert first["capture"]["reachable"] is True
    assert first["generation"] == 1
    assert calls == {"dashboard": 1, "categories": 1, "capture": 1}
