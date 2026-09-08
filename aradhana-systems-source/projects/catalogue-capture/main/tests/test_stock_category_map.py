"""
stock_category_map.py: the 47 real stock categories (from
Aradhana_Categorywise_Varieties.xlsx, verified 2026-07-31 by variety-set
overlap against Stock/31072026.xls) and which ones reuse an existing
background/model asset today.

The 28/19 split is deliberate, not an accident of the source data: a
category is only "ready" when an EXISTING asset genuinely covers its whole
real-world scope. Bali (merges ladies+gents under one category where
today's assets are split) and Chain (not split by gender the way today's
assets are) were explicitly excluded rather than approximated — this test
suite locks that decision in so a future edit can't quietly "fix" it back
to a borrowed/approximate mapping.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import stock_category_map as scm


def test_exactly_57_categories():
    assert len(scm.CATEGORIES) == 57


def test_every_key_and_label_is_unique():
    assert len({c.key for c in scm.CATEGORIES}) == 57
    assert len({c.label for c in scm.CATEGORIES}) == 57


def test_all_current_categories_are_processable():
    assert len(scm.READY) == 57
    assert len(scm.NEEDS_SETUP) == 0


def test_bali_keeps_explicit_calibrated_semantics():
    """Bali keys are separately calibrated; neither may silently fall back
    to a gender-specific legacy alias."""
    assert scm.processing_key("bali_18") == "bali_18"
    assert scm.processing_key("bali_22") == "bali_22"


def test_chain_keeps_explicit_calibrated_semantics_and_legacy_18_works():
    """CHAIN 22 has an explicit unisex calibration. Historical CHAIN 18
    retains its generic compatibility key."""
    assert scm.processing_key("chain_18") == "chain"
    assert scm.processing_key("chain_22") == "chain_22"


def test_ready_categories_resolve_to_a_non_generic_profile_and_model_zone():
    """existing_key is the OLD internal processing key model_engine.py /
    background asset filenames still use — a different namespace from
    capture_tool.CATEGORY_LABELS, which now holds only the new 47 keys.
    model_engine.CATEGORY_TEMPLATES is the actual owner of that namespace."""
    from model_engine import get_templates
    from ornament_placement import normalise_category

    for cat in scm.READY:
        assert normalise_category(cat.existing_key) != "generic"
        assert get_templates(cat.existing_key)["zone"]


def test_ready_categories_have_a_real_background_file():
    import pytest
    engine_cascade = pytest.importorskip(
        "engine_cascade",
        reason="engine_cascade was never committed on this branch lineage (confirmed via git log --all) -- this test targets an archived app.py API surface",
    )

    for cat in scm.READY:
        path = engine_cascade.resolve_category_bg_path(cat.existing_key, "Regular")
        assert path and os.path.isfile(path), f"{cat.key} -> {cat.existing_key}: no background"


def test_is_ready_matches_the_partition():
    for cat in scm.READY:
        assert scm.is_ready(cat.key) is True
    for cat in scm.NEEDS_SETUP:
        assert scm.is_ready(cat.key) is False


def test_unknown_key_is_not_ready_and_has_no_processing_key():
    assert scm.is_ready("not_a_real_category") is False
    assert scm.processing_key("not_a_real_category") is None


# ── match_label / captured_keys ──────────────────────────────────────────────
# These back the dropdown's "auto-enable once real capture activity exists"
# behavior (app.py's index() route) — a needs-setup category should stop
# showing disabled the moment staff actually start capturing it, without
# waiting on a manual existing_key edit here.

def test_match_label_finds_an_exact_label():
    cat = scm.match_label("jhumka 22")
    assert cat is not None and cat.key == "jhumka_22"


def test_match_label_is_none_for_unknown_text():
    assert scm.match_label("something not a category") is None


def test_captured_keys_recognises_leading_tray_number_form(tmp_path):
    (tmp_path / "3 Jhumka 22").mkdir()
    assert scm.captured_keys(str(tmp_path)) == {"jhumka_22"}


def test_captured_keys_recognises_trailing_tray_number_form(tmp_path):
    """Historical per-category numbering, e.g. 'Tikka 18 4' — trailing form."""
    (tmp_path / "Tikka 18 4").mkdir()
    assert scm.captured_keys(str(tmp_path)) == {"tikka_18"}


def test_captured_keys_ignores_files_and_unmatched_folders(tmp_path):
    (tmp_path / "not_a_category.txt").write_text("x")
    (tmp_path / "Some Random Folder").mkdir()
    assert scm.captured_keys(str(tmp_path)) == set()


def test_captured_keys_merges_across_multiple_roots(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "1 Nath 22").mkdir()
    (root_b / "2 Tikka 22").mkdir()
    assert scm.captured_keys(str(root_a), str(root_b)) == {"nath_22", "tikka_22"}


def test_captured_keys_tolerates_a_missing_root(tmp_path):
    missing = tmp_path / "does_not_exist"
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "1 Nath 22").mkdir()
    assert scm.captured_keys(str(missing), str(tmp_path / "real")) == {"nath_22"}
