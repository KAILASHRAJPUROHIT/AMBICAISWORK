from __future__ import annotations

import catalogue_reference_guides
import pytest


def test_bl22_43_uses_reviewed_automatic_angle_guide() -> None:
    guide = catalogue_reference_guides.guide_for("bali_22", "BL22_43")
    assert guide is not None
    assert guide.is_file()
    assert guide.name == "BL22_43_front45.jpg"


def test_all_current_bali_items_have_reviewed_angle_routing() -> None:
    assert len(catalogue_reference_guides.covered_labels()) == 33
    for label in catalogue_reference_guides.covered_labels():
        guide = catalogue_reference_guides.guide_for("bali", label)
        assert guide is not None
        assert guide.is_file()


def test_production_bali_18_and_22_keys_activate_angle_routing() -> None:
    assert catalogue_reference_guides.guide_for("bali_18", "BL18_16") is not None
    assert catalogue_reference_guides.guide_for("bali_22", "BL22_76") is not None


def test_geometry_families_route_to_distinct_guides() -> None:
    huggie = catalogue_reference_guides.guide_for("ladies_bali", "BL18_16")
    hoop = catalogue_reference_guides.guide_for("ladies_bali", "BL22_76")
    assert huggie is not None and huggie.name == "compact_huggie_45.jpg"
    assert hoop is not None and hoop.name == "round_hoop_45.jpg"
    assert huggie != hoop


def test_unknown_bali_item_blocks_before_spend() -> None:
    with pytest.raises(catalogue_reference_guides.MissingBaliAngleProfile, match="BLOCKED_BEFORE_SPEND"):
        catalogue_reference_guides.guide_for("ladies_bali", "BL22_NEW")


def test_guide_is_bali_category_scoped() -> None:
    assert catalogue_reference_guides.guide_for("necklace", "BL22_43") is None
    assert catalogue_reference_guides.guide_for(None, "BL22_43") is None
