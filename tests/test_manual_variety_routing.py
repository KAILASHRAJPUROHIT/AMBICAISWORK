"""_resolve_pair_assets: Manual Mode's own per-pair asset resolution.
Baseline is the existing per-pair
cycling — default False means every job runner's exact current behaviour is
unchanged for an operator who hasn't opted in. When on, a resolved variety
match overrides bg_path/model_cfg for that pair only; anything unresolved
(unknown tag, resolved asset outside MODELS_DIR) falls back to the cycling
baseline, never raises, never blocks a pair that would otherwise work.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import app
import variety_routing


def _cfg(**overrides):
    base = {"enabled": True}
    base.update(overrides)
    return base


def test_off_by_default_uses_existing_cycling(monkeypatch):
    monkeypatch.setattr(variety_routing, "resolve", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must not be called when variety_auto is False")))

    bg_path, model_cfg_i = app._resolve_pair_assets(
        {"pair": 1, "label": "LC22_13"}, 0, "locket",
        ["/bg/cycled_0.jpg", "/bg/cycled_1.jpg"], _cfg(), variety_auto=False,
    )

    assert bg_path == "/bg/cycled_0.jpg"
    assert model_cfg_i == _cfg()


def test_on_and_resolved_overrides_bg_and_model(monkeypatch, tmp_path):
    models_root = tmp_path / "models"
    female_dir = models_root / "female"
    female_dir.mkdir(parents=True)
    resolved_model = female_dir / "hero.jpg"
    resolved_model.write_bytes(b"x")

    monkeypatch.setattr(app, "MODELS_DIR", str(models_root))
    monkeypatch.setattr(
        variety_routing, "resolve",
        lambda tag, cat, **k: variety_routing.VarietyAssets(
            background_path="/bg/variety.jpg",
            model_path=str(resolved_model),
            variety="ANTIQUE",
        ),
    )

    bg_path, model_cfg_i = app._resolve_pair_assets(
        {"pair": 1, "label": "LC22_13"}, 0, "locket", ["/bg/cycled.jpg"], _cfg(), variety_auto=True,
    )

    assert bg_path == "/bg/variety.jpg"
    assert model_cfg_i["modelPath"] == os.path.join("female", "hero.jpg")
    assert model_cfg_i["allowPoseOverride"] is True
    # Baseline dict must not be mutated — _cycled_model_cfg's caller-shared
    # model_cfg (the whole batch's config) must stay untouched by one pair's
    # override.
    assert "modelPath" not in _cfg()


def test_on_but_unresolved_falls_back_to_cycling(monkeypatch):
    monkeypatch.setattr(variety_routing, "resolve", lambda *a, **k: None)

    bg_path, model_cfg_i = app._resolve_pair_assets(
        {"pair": 1, "label": "UNKNOWN"}, 0, "locket", ["/bg/cycled.jpg"], _cfg(), variety_auto=True,
    )

    assert bg_path == "/bg/cycled.jpg"
    assert model_cfg_i == _cfg()


def test_resolved_model_outside_models_dir_falls_back_to_cycling(monkeypatch, tmp_path):
    """A resolved asset outside this app's configured MODELS_DIR cannot be
    expressed through the relative modelPath contract — it must fall back,
    never crash and never get passed through as an unsafe absolute path."""
    models_root = tmp_path / "models"
    models_root.mkdir()
    outside = tmp_path / "elsewhere" / "hero.jpg"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"x")

    monkeypatch.setattr(app, "MODELS_DIR", str(models_root))
    monkeypatch.setattr(
        variety_routing, "resolve",
        lambda tag, cat, **k: variety_routing.VarietyAssets(
            background_path="/bg/variety.jpg", model_path=str(outside), variety="ANTIQUE",
        ),
    )

    bg_path, model_cfg_i = app._resolve_pair_assets(
        {"pair": 1, "label": "LC22_13"}, 0, "locket", ["/bg/cycled.jpg"], _cfg(), variety_auto=True,
    )

    assert bg_path == "/bg/cycled.jpg"
    assert model_cfg_i == _cfg()


def test_variety_auto_reaches_every_manual_job_runner():
    """Structural guard: variety_auto must be a real parameter on every
    manual job runner, and every route that starts one must read
    data.get('varietyAuto') and pass it through — otherwise the feature
    silently works for some entry points and not others, exactly the class
    of bug this codebase has repeatedly shipped."""
    import inspect

    for fn_name in ("_run_chatgpt_job", "_run_copilot_job", "_resolve_pair_assets"):
        params = inspect.signature(getattr(app, fn_name)).parameters
        assert "variety_auto" in params, f"{fn_name} is missing variety_auto"
        assert params["variety_auto"].default is False, (
            f"{fn_name}'s variety_auto must default False — every current "
            f"caller passes it explicitly, so nothing exercises this default "
            f"today, but a future caller that forgets to pass it must not "
            f"silently activate the feature"
        )

    src = inspect.getsource(app)
    # The copilot batch is launched through _guarded_run (a try/finally that
    # always clears CGPT_JOB["running"]), so the call is inside that wrapper
    # rather than in Thread(args=...). The argument ORDER is what this guard
    # actually protects, and it is unchanged.
    assert (
        "_run_copilot_job(pairs, category, bg_names, model_cfg,\n"
        "                             process_mode, variety_auto, cancel_event," in src
    ), "Copilot job call is missing variety_auto before its cancellation arguments"
    assert "threading.Thread(target=_guarded_run, daemon=True).start()" in src, (
        "Copilot batch must start via _guarded_run — launching _run_copilot_job "
        "directly leaves CGPT_JOB['running'] stuck True when the worker raises "
        "before its executor loop, which 409s every later Process click"
    )
    marker = (
        "target=_run_chatgpt_job,\n"
        "        args=(pairs, category, bg_names, model_cfg, process_mode, variety_auto)"
    )
    assert marker in src, f"thread launch missing variety_auto: {marker!r}"

    codex_src = src[src.index("def api_codex_run"):src.index("def api_engine_stats") if "def api_engine_stats" in src else len(src)]
    assert 'variety_auto = bool(data.get("varietyAuto"))' in codex_src
    assert "_resolve_pair_assets(\n                s, idx, category, bg_paths, model_cfg, variety_auto" in codex_src
