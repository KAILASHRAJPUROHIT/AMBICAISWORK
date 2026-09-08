import app


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "INPUT", tmp_path)
    app.JOB["running"] = False
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["authed"] = True
        session["detected_category"] = "tops_22"
        session["category_detection"] = {"category": "tops_22"}
    return client


def test_red_x_endpoint_removes_only_selected_queue_item(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "TP22_1.jpg").write_bytes(b"one")
    (tmp_path / "TP22_2.jpg").write_bytes(b"two")

    response = client.delete("/api/queue/item", json={"name": "TP22_1.jpg"})

    assert response.status_code == 200
    assert not (tmp_path / "TP22_1.jpg").exists()
    assert (tmp_path / "TP22_2.jpg").read_bytes() == b"two"
    assert response.get_json()["remaining"] == 1


def test_clear_all_empties_queue_and_resets_detection(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "TP22_1.jpg").write_bytes(b"one")
    (tmp_path / "TP22_2.png").write_bytes(b"two")

    response = client.post("/api/queue/clear")

    assert response.status_code == 200
    assert response.get_json()["cleared"] == 2
    assert list(tmp_path.iterdir()) == []
    loaded = client.get("/api/load").get_json()
    assert loaded["pairs"] == []
    assert loaded["detected_category"] == {}


def test_queue_cannot_change_during_processing(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "TP22_1.jpg").write_bytes(b"one")
    app.JOB["running"] = True
    try:
        assert client.delete("/api/queue/item", json={"name": "TP22_1.jpg"}).status_code == 409
        assert client.post("/api/queue/clear").status_code == 409
        assert (tmp_path / "TP22_1.jpg").exists()
    finally:
        app.JOB["running"] = False


def test_queue_delete_rejects_path_traversal(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.delete("/api/queue/item", json={"name": "../capture_intake/x.jpg"}).status_code == 400


def test_processed_original_can_be_served_for_side_by_side_review(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    original = processed / "JHUMKA 22" / "JB22_1.jpg"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"raw")
    monkeypatch.setattr(app, "PROCESSED", processed)
    client = _client(tmp_path / "input", monkeypatch)
    (tmp_path / "input").mkdir(exist_ok=True)

    response = client.get("/img/processed/JHUMKA%2022/JB22_1.jpg")

    assert response.status_code == 200
    assert response.data == b"raw"
