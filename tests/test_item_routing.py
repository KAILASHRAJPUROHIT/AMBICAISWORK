from __future__ import annotations

from decimal import Decimal

import item_routing
import stock_excel


def _record(*, variety="ANTIQUE"):
    return stock_excel.StockRecord(
        label_no="LC22/13",
        old_barcode_no="",
        prefix="LC",
        carat="22",
        variety_name=variety,
        gross_weight=Decimal("3.0"),
        net_weight=Decimal("2.8"),
        pieces=1,
        huids=(),
        source_row=2,
    )


def _assets(tmp_path, *, ornament="locket", theme="Regular", pose="neck"):
    backgrounds = tmp_path / "backgrounds"
    models = tmp_path / "models"
    bg = backgrounds / theme / f"bg_{ornament}.jpg"
    bg.parent.mkdir(parents=True)
    bg.write_bytes(b"background")
    model = models / "female" / "legacy" / f"{pose}_front.jpg"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    return backgrounds, models, model


def test_named_variety_only_changes_output_folder(tmp_path):
    backgrounds, models, model = _assets(tmp_path)
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
    )

    decision = router.route(_record(), "Locket")

    # The variety is still resolved and reported, but no longer segments the
    # output tree — deliverables land flat under their category (operator
    # decision, 2026-08-06). Both assertions matter: dropping the folder
    # level must not quietly stop the workbook's variety from being read.
    assert decision.variety == "ANTIQUE"
    assert decision.output_bucket == "ANTIQUE"
    assert decision.studio_output == tmp_path / "output/locket/LC22_13.jpg"
    assert decision.model_output == tmp_path / "output/locket/LC22_13_2.jpg"
    assert decision.background_theme == "Regular"
    assert decision.model_pose == "neck"
    assert decision.model_candidates == (model.resolve(),)
    assert decision.ready


def test_general_ornament_rule_changes_assets_for_every_variety(tmp_path):
    backgrounds, models, model = _assets(
        tmp_path, theme="Antique", pose="neck"
    )
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
        manifest={
            "version": 1,
            "general_by_ornament": {
                "locket": {
                    "background_theme": "Antique",
                    "model_pose": "neck",
                }
            },
        },
    )

    decision = router.route(_record(), "locket")

    assert decision.background_theme == "Antique"
    assert decision.background_path.name == "bg_locket.jpg"
    assert decision.model_candidates == (model.resolve(),)
    assert decision.ready


def test_blank_variety_is_general_with_ornament_theme_and_pose(tmp_path):
    backgrounds, models, _ = _assets(tmp_path)
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
    )

    decision = router.route(_record(variety=None), "locket")

    assert decision.variety == stock_excel.GENERAL_VARIETY
    assert decision.output_bucket == "GENERAL"
    assert decision.background_theme == "Regular"
    assert decision.model_pose == "neck"
    assert decision.ready


def test_manual_override_wins_without_changing_variety_output(tmp_path):
    backgrounds, models, _ = _assets(tmp_path, theme="Highlight", pose="neck")
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
    )

    decision = router.route(
        _record(),
        "locket",
        manual_override={"background_theme": "Highlight"},
    )

    assert decision.background_theme == "Highlight"
    assert decision.output_bucket == "ANTIQUE"
    assert decision.manually_overridden


def test_explicit_model_image_is_validated_inside_model_root(tmp_path):
    backgrounds, models, model = _assets(tmp_path)
    relative = model.relative_to(models).as_posix()
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
        manifest={
            "general_by_ornament": {"locket": {"model_image": relative}},
        },
    )

    decision = router.route(_record(), "locket")

    assert decision.model_image == model.resolve()
    assert decision.model_candidates == (model.resolve(),)


def test_missing_background_fails_loudly(tmp_path):
    backgrounds, models, _ = _assets(tmp_path)
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
        manifest={
            "general_by_ornament": {
                "locket": {"background_theme": "Not A Real Theme"}
            }
        },
    )

    try:
        router.route(_record(), "locket")
    except item_routing.RoutingError as exc:
        assert "No background asset" in str(exc)
    else:
        raise AssertionError("missing background was silently accepted")


def test_unknown_manual_override_field_is_rejected(tmp_path):
    backgrounds, models, _ = _assets(tmp_path)
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
    )

    try:
        router.route(_record(), "locket", manual_override={"category": "new"})
    except item_routing.RoutingError as exc:
        assert "Unknown manual routing" in str(exc)
    else:
        raise AssertionError("unknown override field was accepted")


def test_manifest_rejects_unknown_fields():
    try:
        item_routing.ItemRouter(
            manifest={"general_by_ornament": {"locket": {"magic": "x"}}}
        )
    except item_routing.RoutingError as exc:
        assert "Unknown field" in str(exc)
    else:
        raise AssertionError("unknown manifest field was accepted")


def test_exact_variety_rule_wins_over_general_and_ornament_default(tmp_path):
    backgrounds, models, _ = _assets(tmp_path, theme="Exact", pose="wrist")
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
        manifest={
            "general_by_ornament": {
                "locket": {"background_theme": "Ornament", "model_pose": "ear"}
            },
            "by_ornament_variety": {
                "locket": {
                    "GENERAL": {"background_theme": "General", "model_pose": "hand"},
                    "antique": {"background_theme": "Exact", "model_pose": "wrist"},
                }
            },
        },
    )

    decision = router.route(_record(variety="Antique"), "locket")

    assert decision.background_theme == "Exact"
    assert decision.model_pose == "wrist"


def test_manual_override_wins_over_exact_variety_rule(tmp_path):
    backgrounds, models, _ = _assets(tmp_path, theme="Manual", pose="neck")
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
        manifest={
            "by_ornament_variety": {
                "locket": {
                    "ANTIQUE": {"background_theme": "Exact", "model_pose": "ear"}
                }
            }
        },
    )

    decision = router.route(
        _record(),
        "locket",
        manual_override={"background_theme": "Manual", "model_pose": "neck"},
    )

    assert decision.background_theme == "Manual"
    assert decision.model_pose == "neck"


def test_blank_variety_uses_general_variety_rule(tmp_path):
    backgrounds, models, _ = _assets(tmp_path, theme="General", pose="hand")
    router = item_routing.ItemRouter(
        output_root=tmp_path / "output",
        backgrounds_root=backgrounds,
        models_root=models,
        manifest={
            "by_ornament_variety": {
                "locket": {
                    "general": {"background_theme": "General", "model_pose": "hand"}
                }
            }
        },
    )

    decision = router.route(_record(variety=None), "locket")

    assert decision.variety == "GENERAL"
    assert decision.background_theme == "General"
    assert decision.model_pose == "hand"


def test_structured_background_prefers_exact_variety_then_general(tmp_path):
    backgrounds, models, _ = _assets(tmp_path)
    legacy = backgrounds / "Regular" / "bg_locket.jpg"
    exact = backgrounds / "Regular" / "locket" / "ANTIQUE" / "bg_locket.jpg"
    exact.parent.mkdir(parents=True)
    exact.write_bytes(b"exact")
    general = backgrounds / "Regular" / "locket" / "GENERAL" / "bg_locket.jpg"
    general.parent.mkdir(parents=True)
    general.write_bytes(b"general")
    router = item_routing.ItemRouter(
        backgrounds_root=backgrounds,
        models_root=models,
    )

    assert router.route(_record(variety="Antique"), "locket").background_path == exact.resolve()
    exact.unlink()
    assert router.route(_record(variety="Antique"), "locket").background_path == general.resolve()
    general.unlink()
    assert router.route(_record(variety="Antique"), "locket").background_path == legacy.resolve()


def test_structured_model_prefers_exact_variety_then_general(tmp_path):
    backgrounds, models, legacy = _assets(tmp_path)
    exact = models / "female" / "locket" / "neck" / "ANTIQUE" / "hero.jpg"
    exact.parent.mkdir(parents=True)
    exact.write_bytes(b"exact")
    general = models / "female" / "locket" / "neck" / "GENERAL" / "hero.jpg"
    general.parent.mkdir(parents=True)
    general.write_bytes(b"general")
    router = item_routing.ItemRouter(
        backgrounds_root=backgrounds,
        models_root=models,
    )

    assert router.route(_record(variety="Antique"), "locket").model_candidates == (exact.resolve(),)
    exact.unlink()
    assert router.route(_record(variety="Antique"), "locket").model_candidates == (general.resolve(),)
    general.unlink()
    assert router.route(_record(variety="Antique"), "locket").model_candidates == (legacy.resolve(),)


def test_model_theme_group_hierarchy_is_supported(tmp_path):
    backgrounds, models, _ = _assets(tmp_path)
    themed = (
        models
        / "Traditional"
        / "female"
        / "locket"
        / "neck"
        / "ANTIQUE"
        / "hero.jpg"
    )
    themed.parent.mkdir(parents=True)
    themed.write_bytes(b"themed")
    router = item_routing.ItemRouter(
        backgrounds_root=backgrounds,
        models_root=models,
        manifest={
            "by_ornament_variety": {
                "locket": {"ANTIQUE": {"model_theme": "Traditional"}}
            }
        },
    )

    decision = router.route(_record(), "locket")

    assert decision.model_theme == "Traditional"
    assert decision.model_candidates == (themed.resolve(),)


def test_explicit_background_image_wins_and_is_root_confined(tmp_path):
    backgrounds, models, _ = _assets(tmp_path)
    manual = backgrounds / "manual" / "selected.jpg"
    manual.parent.mkdir(parents=True)
    manual.write_bytes(b"manual")
    router = item_routing.ItemRouter(
        backgrounds_root=backgrounds,
        models_root=models,
    )

    decision = router.route(
        _record(), "locket", manual_override={"background_image": "manual/selected.jpg"}
    )

    assert decision.background_path == manual.resolve()
    try:
        router.route(
            _record(), "locket", manual_override={"background_image": "../escape.jpg"}
        )
    except item_routing.RoutingError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("background path traversal was accepted")


def test_legacy_model_fallback_never_uses_unrelated_or_agnostic_pose(tmp_path):
    backgrounds, models, legacy = _assets(tmp_path, pose="ear")
    (legacy.parent / "portrait.jpg").write_bytes(b"agnostic")
    router = item_routing.ItemRouter(
        backgrounds_root=backgrounds,
        models_root=models,
        manifest={"general_by_ornament": {"locket": {"model_pose": "waist"}}},
    )

    try:
        router.route(_record(), "locket")
    except item_routing.RoutingError as exc:
        assert "No model assets" in str(exc)
        assert "waist" in str(exc)
    else:
        raise AssertionError("an unrelated model pose was silently selected")
