from pathlib import Path
import hashlib

import pytest

import engine_cascade
import app
import model_engine
from jewellery_image_policy import build_studio_edit_prompt
from ornament_placement import (
    background_asset_category,
    get_profile,
    model_guidance,
    normalise_category,
    studio_guidance,
)
from stock_category_map import CATEGORIES


def test_every_stock_category_has_an_operational_profile_and_body_zone():
    failures = []
    for category in CATEGORIES:
        profile = get_profile(category.key)
        templates = model_engine.get_templates(category.key)
        if profile.key == "generic" or not templates.get("zone"):
            failures.append((category.key, profile.key, templates.get("zone")))
    assert failures == []


@pytest.mark.parametrize(
    ("stock_key", "profile_key", "zone", "first_model"),
    [
        ("wati_22", "wati", "neck", "F2"),
        ("mangota_22", "mangota", "wrist", "KG"),
        ("dull_22", "dul", "face", "F1"),
        ("kaan_chain_22", "kaan_chain", "face", "F1"),
        ("baju_bandh_22", "bajuband", "upper_arm", "F2"),
        ("baby_kadli_22", "baby_kadli", "wrist", "KG"),
        ("necklace_set_22", "necklace_set", "neck", "F1"),
        ("pendent_set_22", "pendant_set", "neck", "F1"),
    ],
)
def test_indian_stock_semantics_drive_model_selection(
    stock_key, profile_key, zone, first_model
):
    assert normalise_category(stock_key) == profile_key
    cfg = model_engine.get_templates(stock_key)
    assert cfg["zone"] == zone
    assert cfg["models"][0] == first_model


def test_wati_is_neck_jewellery_and_never_a_bowl_or_toe_ring():
    studio = studio_guidance("WATI 22")
    model = model_guidance("wati_22")
    prompt = model_engine.build_model_prompt("wati_22", "WT22_1", 1)

    assert "NOT a ceremonial bowl" in studio
    assert "NOT a toe ring" in studio
    assert "black-bead mangalsutra" in studio
    assert "married Indian woman's neck" in model
    assert "at the neck" in prompt
    assert "at the feet" not in prompt


def test_category_rules_cover_attachment_and_component_edge_cases():
    assert "earring/lobe" in model_guidance("kaan_chain_22")
    assert "hair pin" in model_guidance("kaan_chain_22")
    assert "upper arm between shoulder and elbow" in model_guidance("baju_bandh_22")
    assert "child's wrist" in model_guidance("mangota_22")
    assert "necklace at the neck" in model_guidance("necklace_set_22")
    assert "matching earrings" in model_guidance("necklace_set_22")
    assert "not worn" in get_profile("gold_coin").wearer


def test_model_edit_keeps_reference_background_and_uses_natural_ear_scale():
    # engine="gemini" explicitly: Copilot (the default) now gets a condensed
    # prompt (see model_engine._build_model_prompt_compact) since its web
    # composer has a much tighter character ceiling than Gemini's.
    prompt = model_engine.build_model_prompt("jhumka_22", "JM22_1", 1, engine="gemini")
    assert "ORIGINAL BACKGROUND pixel-faithfully" in prompt
    assert "IGNORE IT" in prompt
    assert "one ear-height below" in prompt
    assert "Never enlarge earrings" in prompt


def test_studio_prompt_uses_destination_prop_geometry_and_category_rule():
    prompt = build_studio_edit_prompt("jhumka_22", engine="gemini")
    assert "CATEGORY PLACEMENT (Jhumka)" in prompt
    assert "EARRING-STAND RULE" in prompt
    assert "preserve the entire stand" in prompt
    assert "Never remove, replace, repaint or redesign" in prompt
    assert "no readable characters" in prompt


def test_three_image_legacy_prompt_keeps_tag_out_of_destination_role():
    prompt = build_studio_edit_prompt(
        "ladies_rings", engine="copilot", include_tag_image=True
    )
    assert "Image 2: price/tag reference" in prompt
    assert "Image 3: destination studio scene" in prompt
    assert "into Image 3" in prompt
    assert "LABEL: <item code>" in prompt


def test_wati_uses_reviewed_mangalsutra_background_without_deleting_legacy_asset():
    assert background_asset_category("wati") == "mangalsutra_short"
    resolved = engine_cascade.resolve_category_bg_path("wati", "Regular")
    assert resolved is not None
    assert Path(resolved).name == "bg_mangalsutra_short.jpg"
    legacy = Path(engine_cascade.BASE) / "backgrounds" / "Regular" / "bg_wati.jpg"
    assert legacy.is_file()


def test_wati_background_preview_serves_same_reviewed_asset_as_generation():
    root = Path(app.BACKGROUNDS_DIR)
    expected = root / "Regular" / "bg_mangalsutra_short.jpg"
    with app.app.test_client() as client:
        with client.session_transaction() as session:
            session["authed"] = True
        response = client.get("/img/bg/Regular/bg_wati.jpg")

    assert response.status_code == 200
    assert hashlib.sha256(response.data).digest() == hashlib.sha256(
        expected.read_bytes()
    ).digest()


def test_literal_ring_never_substring_matches_earrings():
    assert normalise_category("ring") == "ring"
    cfg = model_engine.get_templates("ring")
    assert cfg["zone"] == "hand"
    assert cfg["zone"] != model_engine.get_templates("earrings")["zone"]


def test_every_current_category_resolves_a_real_regular_background():
    for category in CATEGORIES:
        path = engine_cascade.resolve_category_bg_path(category.existing_key, "Regular")
        assert path and Path(path).is_file(), category.label
