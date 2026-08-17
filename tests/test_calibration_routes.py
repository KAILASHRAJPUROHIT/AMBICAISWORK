"""HTTP routes for RSC 2 category calibration (calibration_repository.py
wired into capture_server.py). Same test-client pattern as
test_capture_tray_routes.py; the repository's own logic is covered in
tests/test_calibration_repository.py, this only checks the HTTP wiring.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


@pytest.fixture
def cal(tmp_path, monkeypatch):
    import calibration_repository as _cal
    repo = _cal.CalibrationRepository(path=str(tmp_path / "calibration.json"))
    monkeypatch.setattr(_cal, "repository", repo)
    return _cal


@pytest.fixture
def client(cal):
    import capture_server
    capture_server.app.config["TESTING"] = True
    c = capture_server.app.test_client()
    with c.session_transaction() as s:
        s["authed"] = True
    return c


def _pose(yaw=0.0, pitch=0.0, roll=0.0):
    return {"yaw": yaw, "pitch": pitch, "roll": roll}


def test_status_reports_all_categories_not_configured_initially(client, cal):
    import ornament_code_map as ocm
    r = client.get("/api/capture/calibration/status")
    body = r.get_json()
    assert body["total"] == len(ocm.CATEGORIES)
    assert body["configured"] == 0


def test_get_missing_profile_returns_404(client):
    r = client.get("/api/capture/calibration/earring_22")
    assert r.status_code == 404
    assert r.get_json()["ok"] is False


def test_save_and_get_profile(client):
    r = client.post("/api/capture/calibration", json={
        "categoryKey": "earring_22",
        "main": _pose(0.4, -12.2, 0.3),
        "angle1": _pose(-27.8, -9.7, 0.5),
        "angle2": _pose(28.1, -9.9, 0.4),
    })
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["ok"] is True
    assert body["profile"]["displayName"] == "EARRING 22"
    assert body["profile"]["status"] == "CALIBRATED"

    r2 = client.get("/api/capture/calibration/earring_22")
    assert r2.get_json()["profile"]["main"]["yaw"] == pytest.approx(0.4)


def test_save_rejects_unknown_category(client):
    r = client.post("/api/capture/calibration", json={
        "categoryKey": "not_a_real_category",
        "main": _pose(), "angle1": _pose(10), "angle2": _pose(-10),
    })
    assert r.status_code == 400


def test_save_warns_on_close_angles_unless_accepted(client):
    r = client.post("/api/capture/calibration", json={
        "categoryKey": "earring_22",
        "main": _pose(0, -12, 0),
        "angle1": _pose(0.4, -12, 0),
        "angle2": _pose(27, -9, 0),
    })
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "angles_too_close"
    assert any("ANGLE_1" in w for w in body["warnings"])

    r2 = client.post("/api/capture/calibration", json={
        "categoryKey": "earring_22",
        "main": _pose(0, -12, 0),
        "angle1": _pose(0.4, -12, 0),
        "angle2": _pose(27, -9, 0),
        "acceptCloseAngles": True,
    })
    assert r2.status_code == 200


def test_copy_profile_route(client):
    client.post("/api/capture/calibration", json={
        "categoryKey": "jhumka_22",
        "main": _pose(0, -12, 0), "angle1": _pose(-27, -9, 0), "angle2": _pose(27, -9, 0),
    })
    r = client.post("/api/capture/calibration/copy", json={
        "sourceCategoryKey": "jhumka_22",
        "destinationCategoryKey": "earring_22",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["profile"]["status"] == "COPIED"
    assert body["profile"]["derivedFromCategoryKey"] == "jhumka_22"


def test_copy_from_uncalibrated_source_returns_404(client):
    r = client.post("/api/capture/calibration/copy", json={
        "sourceCategoryKey": "does_not_exist",
        "destinationCategoryKey": "earring_22",
    })
    assert r.status_code == 404


def test_delete_profile_route(client):
    client.post("/api/capture/calibration", json={
        "categoryKey": "bangle_22",
        "main": _pose(), "angle1": _pose(10), "angle2": _pose(-10),
    })
    r = client.delete("/api/capture/calibration/bangle_22")
    assert r.status_code == 200
    assert client.get("/api/capture/calibration/bangle_22").status_code == 404


def test_export_import_round_trip_via_routes(client):
    client.post("/api/capture/calibration", json={
        "categoryKey": "tops_22",
        "main": _pose(1, 2, 3), "angle1": _pose(4, 5, 6), "angle2": _pose(7, 8, 9),
    })
    export = client.get("/api/capture/calibration/export").get_json()
    assert "tops_22" in export["profiles"]

    r = client.post("/api/capture/calibration/import", json=export)
    assert r.status_code == 200
    assert r.get_json()["imported"] == 0  # already present, overwrite defaults False

    r2 = client.post("/api/capture/calibration/import", json={**export, "overwrite": True})
    assert r2.get_json()["imported"] == 1
