from pathlib import Path

import background_library


def test_all_womens_ear_categories_share_earring_backgrounds(tmp_path):
    for style in ("Antique", "Regular"):
        folder = tmp_path / style
        folder.mkdir()
        (folder / "bg_earrings.jpg").write_bytes(b"ear")
        (folder / "bg_tops.jpg").write_bytes(b"tops")
    for category in ("tops_22", "earring_22", "jhumka_22", "bali_22", "dull_22", "kaan_chain_22", "sui_dhaga_22"):
        matches = background_library.compatible_backgrounds(tmp_path, category)
        assert [row["path"] for row in matches] == [
            "Antique/bg_earrings.jpg",
            "Regular/bg_earrings.jpg",
        ]


def test_non_ear_category_uses_its_canonical_background(tmp_path):
    folder = tmp_path / "Highlight"
    folder.mkdir()
    (folder / "bg_ladies_rings.jpg").write_bytes(b"ring")
    (folder / "bg_earrings.jpg").write_bytes(b"ear")
    assert background_library.keywords_for_category("ladies_ring_22") == ("ladies_rings",)
    matches = background_library.compatible_backgrounds(tmp_path, "ladies_ring_22")
    assert [row["path"] for row in matches] == ["Highlight/bg_ladies_rings.jpg"]


def test_background_api_recurses_and_serves_only_safe_library_files(monkeypatch, tmp_path):
    import app

    folder = tmp_path / "Modern Diamond"
    folder.mkdir()
    (folder / "bg_earrings.jpg").write_bytes(b"image")
    monkeypatch.setattr(app, "BACKGROUNDS", tmp_path)
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["authed"] = True
    body = client.get("/api/backgrounds?category=jhumka_22").get_json()
    assert body["count"] == 1
    assert body["items"][0]["url"].endswith("Modern%20Diamond/bg_earrings.jpg")
    assert client.get(body["items"][0]["url"]).status_code == 200

