import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ornament_code_map as ocm


def test_exactly_57_categories_unique_keys_and_prefixes():
    assert len(ocm.CATEGORIES) == 57
    assert len({c.key for c in ocm.CATEGORIES}) == 57
    assert len({c.prefix for c in ocm.CATEGORIES}) == 57


def test_resolves_real_tag_codes_regardless_of_separator():
    for code, expected_label in [
        ("BG22/58", "BANGLE 22"),
        ("bg22_58", "BANGLE 22"),
        ("LR22-287", "LADIES RING 22"),
        ("CH22 100", "CHAIN 22"),
    ]:
        cat = ocm.category_from_tag_code(code)
        assert cat is not None and cat.label == expected_label


def test_disambiguates_overlapping_gold_coin_prefixes():
    """GC1/GC2/GC5/GC10/GC20 and GCM05/GCM1/GCM2/GCM25/GCM3/GCM5/GCM75 all
    share short prefixes of each other — the longest-match-first ordering
    must resolve each to its own distinct category, not a shorter sibling."""
    cases = {
        "GC1/1": "Gold Coin 1 Gm",
        "GC10/1": "Gold Coin 10 Gm",
        "GC2/1": "Gold Coin 2 Gm",
        "GC20/1": "Gold Coin 20 Gm",
        "GC5/1": "Gold Coin 5 Gm",
        "GCM05/1": "Gold Coin 0.050 M",
        "GCM1/1": "Gold Coin 0.100 M",
        "GCM2/1": "Gold Coin 0.200 M",
        "GCM25/1": "Gold Coin 0.250 M",
        "GCM3/1": "Gold Coin 0.300 M",
        "GCM5/1": "Gold Coin 0.500 M",
        "GCM75/1": "Gold Coin 0.750 M",
        "MS20/1": "MSS-SHORT 20",
        "MS22/1": "MSS-SHORT 22",
    }
    for code, expected in cases.items():
        cat = ocm.category_from_tag_code(code)
        assert cat is not None and cat.label == expected, f"{code} -> {cat}"


def test_unknown_prefix_returns_none():
    assert ocm.category_from_tag_code("ZZ99/1") is None
    assert ocm.category_from_tag_code("") is None
    assert ocm.category_from_tag_code(None) is None
