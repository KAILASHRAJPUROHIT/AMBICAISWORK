import pytest
ab = pytest.importorskip(
    "verified_anchor_ab",
    reason="verified_anchor_ab imports comfy_local_img, which does not exist on disk or in any branch history",
)


def test_all_anchor_prompts_are_short_and_preserve_exact_quantity():
    for case in ab.CASES:
        prompt = ab.anchored_prompt(case)
        assert 45 <= len(prompt.split()) <= 80
        assert f"exactly {case['quantity']}" in prompt


def test_bali_anchor_encodes_verified_two_row_geometry():
    case = next(case for case in ab.CASES if case["id"] == "BL18_4")
    prompt = ab.anchored_prompt(case)
    assert "exactly two parallel rows" in prompt
    assert "exactly three parallel yellow-gold rails" in prompt


def test_raw_scanner_json_is_never_inserted():
    for case in ab.CASES:
        prompt = ab.anchored_prompt(case)
        assert "confidence" not in prompt
        assert "uncertain_features" not in prompt
        assert "review_required" not in prompt
