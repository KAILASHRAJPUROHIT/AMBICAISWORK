import pytest

import jewellery_image_policy as policy


@pytest.mark.parametrize(
    "bbox, expected",
    [
        ((120, 300, 2280, 2100), True),   # 90% wide
        ((240, 300, 2160, 2100), True),   # 80% wide
        ((300, 300, 2100, 2100), True),   # 75% both sides
        ((840, 840, 1560, 1560), False),  # 30%, too small
        ((60, 300, 2340, 2100), False),   # 95%, too large
        ((0, 300, 1920, 2100), False),    # correct fill but clipped edge
    ],
)
def test_studio_fill_gate(bbox, expected):
    result = policy.evaluate_studio_bbox((2400, 2400), bbox)

    assert result.ok is expected
    assert result.verified is True


def test_missing_segmentation_is_unverified_review():
    result = policy.evaluate_studio_bbox((2400, 2400), None)

    assert result.ok is False
    assert result.verified is False


def test_prompt_rules_distinguish_studio_and_model_scale():
    assert "75–90%" in policy.STUDIO_PROMPT_RULES
    assert "does not apply" in policy.MODEL_PROMPT_RULES
