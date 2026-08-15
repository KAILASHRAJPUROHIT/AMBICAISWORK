from __future__ import annotations

import re

import category_geometry_hints


def test_all_bali_categories_receive_the_same_geometry_contract() -> None:
    hints = {
        category_geometry_hints.hint_for("bali"),
        category_geometry_hints.hint_for("bali_18"),
        category_geometry_hints.hint_for("bali_22"),
        category_geometry_hints.hint_for("ladies_bali"),
        category_geometry_hints.hint_for("mens_bali"),
    }
    assert len(hints) == 1
    assert None not in hints


def test_bali_hint_requires_side_view_and_preserves_source_cross_section() -> None:
    hint = category_geometry_hints.hint_for("ladies_bali")
    assert hint is not None
    assert "decisive front three-quarter product view" in hint
    assert "yawed approximately 45 degrees" in hint
    assert "projects as a visibly narrow ellipse" in hint
    assert "side depth" in hint
    assert "hinge, and clasp" in hint
    assert "Image 1 is the exclusive authority" in hint
    assert "Image 2" in hint and "45-degree camera orientation" in hint
    assert "flat planes and crisp corners" in hint
    assert "smooth rounded tubing" in hint


def test_bali_hint_uses_positive_bfl_style_phrasing() -> None:
    hint = category_geometry_hints.hint_for("bali")
    assert hint is not None
    forbidden = re.compile(
        r"\b(not|never|no|zero|without|nothing|don't|doesn't|isn't)\b",
        re.IGNORECASE,
    )
    assert forbidden.search(hint) is None


def test_non_bali_category_has_no_geometry_override() -> None:
    assert category_geometry_hints.hint_for("earrings") is None
    assert category_geometry_hints.hint_for("necklace", "BL22_43") is None
    assert category_geometry_hints.hint_for(None) is None


def test_bl18_10_receives_its_measured_angular_design_contract() -> None:
    hint = category_geometry_hints.hint_for("ladies_bali", "BL18_10")
    assert hint is not None
    assert "compact slim huggie earrings" in hint
    assert "Four planar gold faces meet at crisp right-angle edges" in hint
    assert "exactly two straight parallel columns of many tiny round white diamonds" in hint
    assert "inner opening compact" in hint
    assert "Image 1 exclusively for product identity" in hint
    assert "Image 2 exclusively as the camera-angle" in hint


def test_bl22_43_item_specific_hint_locks_gold_fringe_geometry() -> None:
    hint = category_geometry_hints.hint_for("ladies_bali", "BL22_43")
    assert hint is not None
    assert "gold-only construction" in hint
    assert "exactly four rounded bead finials" in hint
    assert "exactly five articulated gold link chains" in hint
    assert "exactly five terminal gold drops" in hint
    assert "Image 2 is supplied" in hint
    assert "reviewed 45-degree camera orientation" in hint


def test_bl22_43_complete_hint_uses_positive_bfl_style_phrasing() -> None:
    hint = category_geometry_hints.hint_for("ladies_bali", "BL22_43")
    assert hint is not None
    forbidden = re.compile(
        r"\b(not|never|no|zero|without|nothing|don't|doesn't|isn't)\b",
        re.IGNORECASE,
    )
    assert forbidden.search(hint) is None


def test_other_bali_items_do_not_inherit_bl18_10_specific_geometry() -> None:
    hint = category_geometry_hints.hint_for("ladies_bali", "BL18_16")
    assert hint is not None
    assert "BL18_10" not in hint
    assert "exactly two parallel rows" not in hint


def test_bl18_10_complete_hint_uses_positive_bfl_style_phrasing() -> None:
    hint = category_geometry_hints.hint_for("ladies_bali", "BL18_10")
    assert hint is not None
    forbidden = re.compile(
        r"\b(not|never|no|zero|without|nothing|don't|doesn't|isn't)\b",
        re.IGNORECASE,
    )
    assert forbidden.search(hint) is None
