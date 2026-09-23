from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v2_process_ui_is_azure_only_and_password_gated():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert "Catalogue Studio" in html and "V2" in html
    assert "Azure FLUX.2 Pro" in html
    assert 'type="password"' in html
    assert "/api/process/start" in html
    for retired in ("Copilot", "Gemini", "ChatGPT", "Codex", "Ollama", "ComfyUI", "Klein"):
        assert retired not in html


def test_v2_operations_keeps_pipeline_controls_without_provider_router():
    html = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
    for endpoint in (
        "/api/pipeline/dashboard",
        "/api/pipeline/category_breakdown",
        "/api/pipeline/requeue",
        "/api/pipeline/processed_reset",
    ):
        assert endpoint in html
    for retired in ("Copilot", "Gemini", "ChatGPT", "Codex", "Ollama", "ComfyUI", "Klein"):
        assert retired not in html


def test_launcher_has_no_local_or_legacy_provider_bootstrap():
    launcher = (ROOT / "launch_catalog_ui.ps1").read_text(encoding="utf-8")
    assert "azure_flux2_pro" in launcher
    for retired in ("copilot", "gemini", "chatgpt", "codex", "ollama", "comfy", "klein"):
        assert retired not in launcher.lower()


def test_catalogue_has_fixed_lan_port_and_binding():
    application = (ROOT / "app.py").read_text(encoding="utf-8")
    launcher = (ROOT / "launch_catalog_ui.ps1").read_text(encoding="utf-8")
    assert 'CATALOGUE_PORT", "7654"' in application
    assert 'host="0.0.0.0"' in application
    assert "$port = 7654" in launcher
    assert "_free_port" not in application


def test_finished_outputs_are_clickable_and_batch_review_is_automatic():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    for required in (
        'id="imageDialog"',
        'id="batchReviewDialog"',
        'id="reviewRaw"',
        'id="reviewOutput"',
        "showFullscreen",
        "openBatchReview(rows)",
        'class="result-open"',
    ):
        assert required in html


def test_raw_and_finished_review_images_have_independent_zoom_and_pan():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    for required in (
        'id="zoomRaw"',
        'id="zoomOutput"',
        'id="zoomIn"',
        'id="zoomOut"',
        'id="zoomReset"',
        'id="imageStage"',
        "changeZoom",
        "pointermove",
    ):
        assert required in html


def test_catalogue_prompt_requires_shadow_free_white_field():
    prompt = (ROOT / "config" / "flux2_pro_catalogue_prompt.txt").read_text(encoding="utf-8")
    assert "seamless pure white background" in prompt
    assert "soft minimal contact shadow" not in prompt


def test_tablet_delivery_keeps_one_megabyte_hard_cap():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "requested_edge = 3200" in source
    assert "target_size=(edge, edge)" in source
    assert "sharpen=True" in source
    assert "maximum_file_bytes=1_000_000" in source
    assert "resolution_adjusted" in source
