"""serve_image()'s roots dict was missing a "models" entry even though
/api/model_images returns paths meant to be served through /img/models/<name>
-- a latent bug invisible until the model library actually had files in it.
"""
from pathlib import Path

import app as catalogue_app


def _client():
    client = catalogue_app.app.test_client()
    with client.session_transaction() as session:
        session["authed"] = True
    return client


def test_models_root_serves_a_real_file(tmp_path, monkeypatch):
    fake_models = tmp_path / "models"
    (fake_models / "kids").mkdir(parents=True)
    (fake_models / "kids" / "pose1.jpg").write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    monkeypatch.setattr(catalogue_app, "MODELS_DIR", str(fake_models))

    response = _client().get("/img/models/kids/pose1.jpg")
    assert response.status_code == 200
    assert response.data == b"\xff\xd8\xff\xe0fakejpeg"


def test_models_root_404s_for_a_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(catalogue_app, "MODELS_DIR", str(tmp_path / "models"))
    response = _client().get("/img/models/does-not-exist.jpg")
    assert response.status_code == 404


def test_models_root_blocks_path_escape(tmp_path, monkeypatch):
    fake_models = tmp_path / "models"
    fake_models.mkdir()
    monkeypatch.setattr(catalogue_app, "MODELS_DIR", str(fake_models))
    response = _client().get("/img/models/..%2f..%2fapp.py")
    assert response.status_code == 404
