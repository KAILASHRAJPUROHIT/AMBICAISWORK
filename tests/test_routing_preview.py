from __future__ import annotations

from decimal import Decimal

import pytest

import app
import item_routing
import routing_preview
import stock_excel


def _record(variety="ANTIQUE"):
    return stock_excel.StockRecord(
        label_no="LC22/13",
        old_barcode_no="",
        prefix="LC",
        carat="22",
        variety_name=variety,
        gross_weight=Decimal("3.0"),
        net_weight=Decimal("2.8"),
        pieces=1,
        huids=(),
        source_row=2,
    )


class _Stock:
    def __init__(self, record=None, refresh_error=None):
        self.record = record
        self.refresh_error = refresh_error
        self.refresh_calls = 0

    def refresh(self):
        self.refresh_calls += 1
        if self.refresh_error:
            raise self.refresh_error

    def lookup(self, label):
        if self.record and label.casefold() in {"lc22/13", "lc22_13"}:
            return self.record
        return None


def _service(tmp_path, *, stock=None, manifest=None):
    backgrounds = tmp_path / "backgrounds"
    models = tmp_path / "models"
    background = backgrounds / "Regular" / "bg_locket.jpg"
    background.parent.mkdir(parents=True)
    background.write_bytes(b"background")
    model = models / "female" / "legacy" / "neck_front.jpg"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
        manifest=manifest,
    )
    return routing_preview.RoutingPreviewService(
        stock=stock or _Stock(_record()),
        router=router,
    )


def _client(monkeypatch, service, *, authenticated=True):
    monkeypatch.setattr(app, "_get_routing_preview_service", lambda: service)
    client = app.app.test_client()
    if authenticated:
        with client.session_transaction() as session:
            session["authed"] = True
    return client


def test_shared_preview_refreshes_stock_and_returns_only_relative_paths(tmp_path):
    stock = _Stock(_record())
    service = _service(tmp_path, stock=stock)

    result = service.preview(tag_label="LC22_13", ornament_type="Locket")

    assert stock.refresh_calls == 1
    assert result["tag_label"] == "LC22/13"
    assert result["variety"] == "ANTIQUE"
    assert result["output_bucket"] == "ANTIQUE"
    # Flat category layout — variety is reported above but does not nest.
    assert result["output"] == {
        "studio": "locket/LC22_13.jpg",
        "model": "locket/LC22_13_2.jpg",
    }
    assert result["background"] == {
        "theme": "Regular",
        "path": "Regular/bg_locket.jpg",
    }
    assert result["model"] == {
        "theme": "",
        "group": "female",
        "pose": "neck",
        "candidates": ["female/legacy/neck_front.jpg"],
    }
    assert result["manually_overridden"] is False
    assert str(tmp_path) not in repr(result)


def test_manual_override_uses_same_contract_and_wins(tmp_path):
    service = _service(tmp_path)
    background = service.router.backgrounds_root / "Highlight" / "bg_locket.jpg"
    background.parent.mkdir(parents=True)
    background.write_bytes(b"highlight")
    model = service.router.models_root / "female" / "legacy" / "hand_front.jpg"
    model.write_bytes(b"hand")

    result = service.preview(
        tag_label="LC22/13",
        ornament_type="locket",
        manual_override={"background_theme": "Highlight", "model_pose": "hand"},
    )

    assert result["background"]["theme"] == "Highlight"
    assert result["model"]["pose"] == "hand"
    assert result["model"]["candidates"] == ["female/legacy/hand_front.jpg"]
    assert result["manually_overridden"] is True


def test_blank_variety_remains_general(tmp_path):
    service = _service(tmp_path, stock=_Stock(_record(None)))

    result = service.preview(tag_label="LC22/13", ornament_type="locket")

    assert result["variety"] == "GENERAL"
    assert result["output_bucket"] == "GENERAL"


def test_unknown_tag_is_404_at_service_boundary(tmp_path):
    service = _service(tmp_path, stock=_Stock())

    with pytest.raises(routing_preview.RoutingPreviewTagNotFound):
        service.preview(tag_label="UNKNOWN", ornament_type="locket")


@pytest.mark.parametrize(
    "payload",
    [
        {"tag_label": "", "ornament_type": "locket"},
        {"tag_label": "LC22/13", "ornament_type": "mystery"},
        {
            "tag_label": "LC22/13",
            "ornament_type": "locket",
            "manual_override": {"unknown": "value"},
        },
        {
            "tag_label": "LC22/13",
            "ornament_type": "locket",
            "manual_override": {"model_image": "../outside.jpg"},
        },
        {
            "tag_label": "LC22/13",
            "ornament_type": "locket",
            "manual_override": {"background_theme": "C:outside"},
        },
        {
            "tag_label": "LC22/13",
            "ornament_type": "locket",
            "manual_override": {"model_pose": "unrelated"},
        },
    ],
)
def test_invalid_category_and_overrides_are_400_class(tmp_path, payload):
    with pytest.raises(routing_preview.RoutingPreviewValidationError):
        _service(tmp_path).preview(**payload)


def test_missing_asset_is_conflict_without_absolute_path_leak(tmp_path):
    service = _service(tmp_path)
    (service.router.backgrounds_root / "Regular" / "bg_locket.jpg").unlink()

    with pytest.raises(routing_preview.RoutingPreviewConflict) as caught:
        service.preview(tag_label="LC22/13", ornament_type="locket")

    assert str(tmp_path) not in str(caught.value)
    assert "compatible asset route" in str(caught.value)


def test_api_success_error_statuses_and_authentication(tmp_path, monkeypatch):
    service = _service(tmp_path)
    client = _client(monkeypatch, service)
    success = client.post(
        "/api/pipeline/routing/preview",
        json={"tag_label": "LC22_13", "ornament_type": "locket"},
    )
    assert success.status_code == 200
    assert success.get_json()["background"]["path"] == "Regular/bg_locket.jpg"

    unknown = _client(monkeypatch, _service(tmp_path / "unknown", stock=_Stock())).post(
        "/api/pipeline/routing/preview",
        json={"tag_label": "missing", "ornament_type": "locket"},
    )
    invalid = client.post(
        "/api/pipeline/routing/preview",
        json={"tag_label": "LC22/13", "ornament_type": "invalid"},
    )
    assert unknown.status_code == 404
    assert invalid.status_code == 400

    unauthenticated = _client(monkeypatch, service, authenticated=False).post(
        "/api/pipeline/routing/preview",
        json={"tag_label": "LC22/13", "ornament_type": "locket"},
    )
    assert unauthenticated.status_code == 401


def test_api_asset_conflict_is_409_and_safe(tmp_path, monkeypatch):
    service = _service(tmp_path)
    (service.router.backgrounds_root / "Regular" / "bg_locket.jpg").unlink()
    response = _client(monkeypatch, service).post(
        "/api/pipeline/routing/preview",
        json={"tag_label": "LC22/13", "ornament_type": "locket"},
    )

    assert response.status_code == 409
    assert str(tmp_path) not in response.get_data(as_text=True)
