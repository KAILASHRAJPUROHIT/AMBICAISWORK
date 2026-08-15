from pathlib import Path
import hashlib

import pytest

import engine_cascade
import app
import model_engine
from jewellery_image_policy import (
    build_klein_edit_prompt,
    build_klein_isolation_prompt,
    build_klein_raw_edit_prompt,
    build_klein_white_product_prompt,
    build_studio_edit_prompt,
)
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


@pytest.mark.parametrize(
    ("folder_name", "expected"),
    [
        ("32 JHUMKA 22", "jhumka"),
        ("56 TOPS 22", "tops"),
        ("6 BALI 22", "bali"),
        ("16 GENTS RING 22", "gents_rings"),
    ],
)
def test_numbered_stock_folder_resolves_for_live_klein_prompt(folder_name, expected):
    assert normalise_category(folder_name) == expected
    assert "unclassified jewellery" not in build_klein_isolation_prompt(folder_name)


def test_klein_ring_prompts_lock_band_topology_and_real_stand():
    isolation = build_klein_isolation_prompt("LADIES RING 22")
    composite = build_klein_edit_prompt("LADIES RING 22")
    for prompt in (isolation, composite):
        assert "continuous finger band/shank" in prompt
        assert "Never flatten it into a brooch" in prompt
        assert "Add no text, logo, watermark, label or AI badge" in prompt
    assert "CATEGORY PLACEMENT (Ladies Ring)" in composite
    assert "Do not erase, replace, resize or redesign the existing stand" in composite
    assert "Preserve every visible band path and its crossing order" in composite
    assert "open bypass or wraparound ring" in composite
    assert "reflective two-tone metal endcaps" in composite
    assert "never replace them with diamonds or gems" in composite


def test_klein_direct_ring_prompt_is_short_positive_and_source_led():
    prompt = build_klein_raw_edit_prompt("LADIES RING 22")
    assert 30 <= len(prompt.split()) <= 80
    assert prompt.startswith("Place the exact")
    assert "left reference" in prompt
    assert "right scene" in prompt
    assert "Keep the jewellery design unchanged" in prompt
    assert "Match only the destination lighting" in prompt
    assert "do not" not in prompt.lower()
    assert "never" not in prompt.lower()


def test_klein_jhumka_composite_keeps_complete_top_to_bottom_assembly():
    prompt = build_klein_edit_prompt("32 JHUMKA 22")
    assert 30 <= len(prompt.split()) <= 80
    assert "hanging from the two ends of the T-stand" in prompt
    assert "complete top-to-bottom assembly" in prompt
    assert "through every connector and bell" in prompt
    assert "lowest bead fringe" in prompt
    assert "equal size and identical design" in prompt
    assert "do not" not in prompt.lower()
    assert "never" not in prompt.lower()


@pytest.mark.parametrize(
    ("category", "placement", "structure"),
    [
        ("TOPS 18", "pinned flat", "front-facing studs"),
        ("JHUMKA 22", "hanging", "lowest bead fringe"),
        ("EARRING 22", "hanging", "lowest drop"),
        ("LADIES BALI 22", "hanging", "circular openings"),
    ],
)
def test_klein_earring_prompts_are_short_positive_and_type_specific(
    category, placement, structure
):
    isolation = build_klein_isolation_prompt(category)
    edit = build_klein_edit_prompt(category)
    for prompt in (isolation, edit):
        assert 30 <= len(prompt.split()) <= 80
        assert "do not" not in prompt.lower()
        assert "never" not in prompt.lower()
    assert placement in edit
    assert structure in edit


@pytest.mark.parametrize(
    "category",
    ["LADIES RING 22", "TOPS 18", "JHUMKA 22", "EARRING 22", "LADIES BALI 22"],
)
def test_klein_white_product_prompts_follow_length_and_positive_rules(category):
    prompt = build_klein_white_product_prompt(category)
    assert 30 <= len(prompt.split()) <= 80
    assert "white" in prompt.lower()
    assert "do not" not in prompt.lower()
    assert "never" not in prompt.lower()


def test_klein_white_prompt_injects_only_surgical_design_facts():
    design = {
        "item_type": "gold infinity stud earrings",
        "quantity": 2,
        "pair": True,
        "silhouette": "horizontal infinity with a crown",
        "components": [
            {"name": "stone crown", "shape": "five marquise stones"},
            {"name": "infinity body", "shape": "crossing gold loop"},
        ],
        "stone_groups": [
            {"where": "each crown", "count": 5, "cut": "marquise", "colour": "colourless"},
        ],
        "metal_colour": "two-tone yellow and white gold",
        "colours_present": ["yellow gold", "colourless white stones"],
    }
    prompt = build_klein_white_product_prompt("TOPS 18", design)
    assert 50 <= len(prompt.split()) <= 80
    assert "exactly 2 separate matching" in prompt
    assert "five marquise stones" in prompt
    assert "exactly 5 colourless marquise stones" in prompt
    assert "infinity body" in prompt
    assert "do not" not in prompt.lower()
    assert "never" not in prompt.lower()


def test_every_current_category_resolves_a_real_regular_background():
    for category in CATEGORIES:
        path = engine_cascade.resolve_category_bg_path(category.existing_key, "Regular")
        assert path and Path(path).is_file(), category.label
