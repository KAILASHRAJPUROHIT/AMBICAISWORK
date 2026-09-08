import antigravity_design_scanner as scanner


def _record(quantity=2, metal="yellow gold", components=None, uncertain=None):
    return {
        "item_type": "bali",
        "quantity": quantity,
        "metal_colour": metal,
        "components": components or [],
        "uncertain_features": uncertain or [],
        "confidence": 0.95,
        "review_required": False,
    }


def test_model_router_uses_gemini_only_for_simple_studs():
    assert scanner.model_for_category("55 TOPS 18") == scanner.MODEL_GEMINI
    assert scanner.model_for_category("ladies ring") == scanner.MODEL_SONNET
    assert scanner.model_for_category("bali") == scanner.MODEL_SONNET


def test_hard_signature_detects_two_rows_and_three_rails():
    record = _record(components=[
        {"name": "upper stone row", "count": 1},
        {"name": "lower stone row", "count": 1},
        {"name": "gold rails", "count": 3},
    ])
    assert scanner.hard_signature(record)["stone_rows"] == 2
    assert scanner.hard_signature(record)["rails"] == 3


def test_dual_scan_blocks_identity_count_conflict():
    two_rows = _record(components=[{"name": "stone rows", "count": 2}])
    three_rows = _record(components=[{"name": "stone rows", "count": 3}])
    merged = scanner.merge_dual(two_rows, three_rows, "bali")
    assert merged["auto_approved"] is False
    assert merged["review_required"] is True
    assert any("stone_rows" in conflict for conflict in merged["scanner"]["conflicts"])


def test_model_confidence_cannot_override_identity_uncertainty():
    record = _record(uncertain=["Exact scroll count hidden by tag"])
    normalized = scanner.normalize_record(record, "locket")
    assert normalized["review_required"] is True
    assert normalized["scanner_identity_uncertain"] is True
    assert normalized["confidence"] == 0.80


def test_material_conflict_is_blocking():
    gold = _record(metal="yellow gold")
    two_tone = _record(metal="yellow gold and white rhodium metal")
    conflicts = scanner.compare_records(gold, two_tone)
    assert any("material" in conflict for conflict in conflicts)
