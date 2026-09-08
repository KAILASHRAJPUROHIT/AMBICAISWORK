import io

import app
import stock_category_map


def test_numbered_folder_path_resolves_current_category():
    category = stock_category_map.category_from_path(
        r"C:\capture_intake\56 TOPS 22\TP22_351.jpg"
    )
    assert category is not None
    assert category.key == "tops_22"


def test_output_category_folder_matches_catalogue_layout():
    assert app._category_output_folder("jhumka_22") == "JHUMKA 22"
    assert app.OUTPUT.name == "output"


def test_daily_stock_tag_and_folder_agree():
    result = app._detect_upload_category(
        ["BG22_1.jpg"], ["7 BANGLE 22/BG22_1.jpg"], "7 BANGLE 22"
    )
    assert result["category"] == "bangle_22"
    assert result["source"] == "folder + daily stock"
    assert result["stock_workbook"].endswith((".xls", ".xlsx"))


def test_daily_stock_and_path_conflict_fails_closed():
    result = app._detect_upload_category(
        ["BG22_1.jpg"], ["56 TOPS 22/BG22_1.jpg"], "56 TOPS 22"
    )
    assert result["status"] == 409
    assert "folder says TOPS 22" in result["error"]
    assert "stock says BANGLE 22" in result["error"]


def test_tag_prefix_is_category_fallback(monkeypatch):
    import stock_excel

    monkeypatch.setattr(stock_excel, "load_stock_label_categories", lambda _path: {})
    result = app._detect_upload_category(["JB22_999999.jpg"], ["JB22_999999.jpg"], "")
    assert result["category"] == "jhumka_22"
    assert result["source"] == "tag prefix"


def test_load_backfills_detection_for_existing_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "INPUT", tmp_path)
    (tmp_path / "JB22_40.jpg").write_bytes(b"image")
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["authed"] = True
        session["category_detection"] = {}
    loaded = client.get("/api/load").get_json()
    assert loaded["detected_category"]["category"] == "jhumka_22"


def test_upload_returns_and_persists_detected_category(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "INPUT", tmp_path)
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["authed"] = True
    response = client.post(
        "/api/upload",
        data={
            "files": (io.BytesIO(b"image"), "BG22_1.jpg"),
            "relative_paths": "7 BANGLE 22/BG22_1.jpg",
            "folder_name": "7 BANGLE 22",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["detected_category"]["category"] == "bangle_22"
    loaded = client.get("/api/load").get_json()
    assert loaded["detected_category"]["category"] == "bangle_22"
