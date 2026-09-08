from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "index.html"


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _javascript(html: str) -> str:
    return "\n".join(
        re.findall(r"<script[^>]*>([\s\S]*?)</script>", html, flags=re.IGNORECASE)
    )


def test_process_panel_has_only_process_pause_and_cancel_controls():
    html = _html()
    panel = html[html.index('<div class="process-panel" id="processSection">'):]
    panel = panel[:panel.index('<!-- AUTO MODE STATUS CHIP -->')]

    # Three controls only. Piece count, relationship and the topology
    # checkboxes were removed on purpose: they are constants of the CATEGORY
    # (see category_topology.py), and asking an operator to re-enter a
    # constant every batch is how it eventually gets entered wrong.
    assert '> Process\n' in panel
    assert '> Pause\n' in panel
    assert '> Cancel\n' in panel
    assert 'id="stopBtn"' in panel and 'disabled' in panel
    assert 'id="pauseBtn"' in panel
    assert 'CONFIRMED SKU PIECES' not in panel
    assert 'topologyPieceCount' not in panel
    assert 'topologyEngineMode' not in panel
    assert '2 Image Mode' not in panel
    assert 'AI Process Only' not in panel
    assert 'id="pill-codex"' not in panel
    assert 'id="pill-chatgpt"' not in panel
    assert 'id="pill-copilot"' not in panel
    assert "const _runMethod = 'copilot'" in html
    assert "const _processMode = 'ai_only'" in html


def test_dashboard_template_javascript_is_syntactically_valid():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")

    result = subprocess.run(
        [node, "--check", "-"],
        input=_javascript(_html()),
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_pipeline_dashboard_has_all_required_metrics_and_bounded_polling():
    html = _html()

    for element_id in (
        "pipeCapturedToday",
        "pipeCapturedTotal",
        "pipeStockTags",
        "pipeStockPieces",
        "pipeProcAvail",
        "pipeProcessedTotal",
        "pipeNeedsReview",
        "pipeRejected",
        "pipeLastCap",
        "pipeLastProc",
        "pipeHealthSegments",
        "pipeImagePolicyList",
    ):
        assert f'id="{element_id}"' in html

    assert "new AbortController()" in html
    assert "if (pending) return" in html
    assert "setTimeout(() => controller.abort(), 1500)" in html
    assert "if (!response.ok) throw new Error('HTTP ' + response.status)" in html
    assert "segments.replaceChildren()" in html
    assert "badge.appendChild(document.createTextNode(' ' + key))" in html
    assert "PIPELINE_LIVE_POLL_MS = 1000" in html
    assert "fetch('/api/pipeline/live_snapshot'" in html
    assert "if (_pipelineLiveRequest) return _pipelineLiveRequest" in html
    assert "if (document.hidden && !force) return" in html


def test_category_breakdown_has_full_width_and_explicit_counts():
    html = _html()

    assert 'id="categoryBreakdownPanel"' in html
    assert 'max-width:1180px' in html
    assert 'id="categoryCapturedSummary"' in html
    assert 'id="categoryFilterCaptured"' in html
    assert 'id="categoryFilterAll"' in html
    assert "category-breakdown-header" in html
    assert "category-count" in html
    assert "capturedTotal = rows.reduce" in html
    assert 'id="pipeStockUpdated"' in html
    assert "stockUpdated + stockSource" in html
    assert "`${value}/${denominator}`" in html
    assert "value / denominator" in html


def test_processed_memory_controls_are_recoverable_and_explicitly_confirmed():
    html = _html()

    for element_id in (
        "processedStatePanel", "processedResetTags", "previewProcessedReset",
        "resetAllProcessed", "processedResetResult",
    ):
        assert f'id="{element_id}"' in html
    assert "/api/pipeline/processed_reset/preview?" in html
    assert "'/api/pipeline/processed_reset'" in html
    assert "RESET ALL PROCESSED" in html
    assert "RESET SELECTED PROCESSED" in html
    assert "Master capture and finished output images are never deleted" in html
    assert "LR22_40-LR22_69" in html


def test_capture_server_summary_is_compact_and_folder_routing_is_expandable():
    html = _html()

    assert 'id="captureActiveTrayCount"' in html
    assert 'id="captureTrayDetails"' in html
    assert '<summary>View active folder routing</summary>' in html
    assert "row.className = 'capture-tray-row'" in html
    assert "trayCount.textContent = String(entries.length)" in html


def test_landing_mode_cards_use_one_responsive_grid_without_forced_viewport_height():
    html = _html()

    assert 'class="mode-select-grid"' in html
    assert html.count("mode-select-card") >= 3
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in html
    assert "min-height:70vh" not in html


def test_manual_pose_override_is_explicit_and_never_leaks_to_auto_mode():
    html = _html()

    assert 'id="allowAllPosesToggle"' in html
    assert "params.set('include_all_poses', '1')" in html
    assert "cfg.allowPoseOverride = true" in html
    assert "const model = _getModelConfig(true)" in html
    assert "model:    _getModelConfig(false)" in html
    assert "Continue with these non-standard model poses?" in html
    assert "zoneBadge.textContent = 'zone: ' + zone" in html


def test_image_policy_fallback_is_configuration_not_an_invented_pass():
    html = _html()

    assert "2400 × 2400" in html
    assert "centered crop for studio + model" in html
    assert "75–90%" in html
    assert "natural worn size" in html
    assert "AI provenance metadata" in html
    assert "return 'UNVERIFIED'" in html


def test_quality_card_renders_live_latest_capture_tag_and_preview():
    html = _html()

    for element_id in (
        "pipeLastCaptureItem", "pipeLastCapturePreview", "pipeLastCaptureTag",
    ):
        assert f'id="{element_id}"' in html
    assert "data.latest_capture" in html
    assert "latest.preview_url" in html


def test_requeue_panel_present_with_both_tabs_and_confirm_box():
    html = _html()

    for element_id in (
        "requeuePanel", "requeueTabNeedsReview", "requeueTabRejected",
        "requeueList", "requeueConfirm",
    ):
        assert f'id="{element_id}"' in html


def test_requeue_uses_the_lifecycle_endpoints_read_then_confirm():
    html = _html()

    assert "'/api/pipeline/requeue?status='" in html
    assert "'/api/pipeline/requeue/preview?'" in html
    assert "fetchBounded('/api/pipeline/requeue', {" in html
    assert "method: 'POST'" in html
    assert "confirmation_token: token" in html


def test_requeue_never_fires_without_an_explicit_confirm_click():
    html = _html()

    # Preview only populates the confirm box; the POST is reachable solely
    # from a listener on the confirm button built inside renderRequeueConfirm.
    assert "confirmBtn.addEventListener('click', () => doRequeue(relativePath, data.confirmation_token))" in html
    assert "async function startRequeuePreview" in html
    preview_fn = html[html.index("async function startRequeuePreview"):html.index("async function doRequeue")]
    assert "doRequeue(" not in preview_fn, (
        "the preview call path must never call doRequeue directly — only the "
        "confirm button's own click listener may"
    )


def test_requeue_surfaces_conflicts_and_disables_confirm():
    html = _html()

    assert "confirmBtn.disabled = !data.can_requeue" in html
    assert "data.conflict || 'This item cannot be requeued right now.'" in html
    assert "'Destination exists'" in html


def test_requeue_polling_is_bounded_and_single_flight():
    html = _html()

    requeue_iife = html[html.index("Requeue: Needs Review"):]
    assert "new AbortController()" in requeue_iife
    assert "setTimeout(() => controller.abort(), 5000)" in requeue_iife
    assert "if (listPending) return" in requeue_iife
    assert "if (previewPending) return" in requeue_iife
    assert "if (confirmPending) return" in requeue_iife


def test_requeue_dom_construction_avoids_html_injection():
    html = _html()

    requeue_iife = html[html.index("Requeue: Needs Review"):html.index("Default view on load")]
    assert "innerHTML" not in requeue_iife
    assert "insertAdjacentHTML" not in requeue_iife
    assert "createElement" in requeue_iife
    assert "textContent" in requeue_iife


def test_requeue_success_refreshes_the_pipeline_dashboard():
    html = _html()

    assert "window.__refreshPipelineDashboard = () => pollDashboard(true)" in html
    assert "window.__refreshPipelineDashboard()" in html


def test_manual_variety_auto_toggle_reaches_the_run_request():
    html = _html()

    assert 'id="manualVarietyAuto"' in html
    assert "varietyAuto: !!document.getElementById('manualVarietyAuto')?.checked" in html


def test_routing_preview_panel_uses_the_authoritative_endpoint_read_only():
    html = _html()

    assert 'id="routingPreviewTag"' in html
    assert 'id="routingPreviewResult"' in html
    assert "fetch('/api/pipeline/routing/preview'" in html
    assert "method: 'POST'" in html

    preview_fn = html[html.index("async function previewVarietyRouting"):
                       html.index("function _setRunning")]
    assert "innerHTML" not in preview_fn
    assert "insertAdjacentHTML" not in preview_fn
    assert "createElement" in preview_fn


def test_routing_preview_surfaces_backend_errors_not_a_generic_failure():
    """404 (tag not in stock) and 409 (no compatible asset) must reach the
    operator as the real reason, not a swallowed generic message."""
    html = _html()
    preview_fn = html[html.index("async function previewVarietyRouting"):
                       html.index("function _setRunning")]
    assert "data.error || ('HTTP ' + r.status)" in preview_fn


def test_category_dropdown_disables_needs_setup_categories():
    """Renders the real page through Flask (not just static template text) —
    catches drift between stock_category_map.NEEDS_SETUP and what the
    dropdown actually marks disabled, which a plain string-in-template check
    would miss entirely."""
    import app as _app

    _app.app.config["TESTING"] = True
    client = _app.app.test_client()
    with client.session_transaction() as s:
        s["authed"] = True
    html = client.get("/").get_data(as_text=True)

    import re
    match = re.search(r'<select id="catSelect".*?</select>', html, re.S)
    assert match, "catSelect dropdown not found in rendered page"
    select_html = match.group(0)

    import raw_intake_sync as ris
    import stock_category_map as scm
    captured = scm.captured_keys(ris.CAPTURE_INTAKE_SOURCE, ris.RAW_FINAL_DIR)
    still_disabled = [c for c in scm.NEEDS_SETUP if c.key not in captured]
    now_enabled = [c for c in scm.NEEDS_SETUP if c.key in captured]

    assert select_html.count(" disabled>") == len(still_disabled)
    for cat in still_disabled:
        assert f'value="{cat.key}" disabled' in select_html
    for cat in scm.READY:
        assert f'value="{cat.key}">' in select_html
        assert f'value="{cat.key}" disabled' not in select_html
    for cat in now_enabled:
        assert f'value="{cat.key}">' in select_html
        assert f'value="{cat.key}" disabled' not in select_html


def test_all_current_stock_categories_are_enabled_without_capture_side_effects():
    """The current 57-category taxonomy has complete semantic/asset routing."""
    import app as _app
    import stock_category_map as scm

    _app.app.config["TESTING"] = True
    client = _app.app.test_client()
    with client.session_transaction() as s:
        s["authed"] = True
    html = client.get("/").get_data(as_text=True)

    import re
    match = re.search(r'<select id="catSelect".*?</select>', html, re.S)
    select_html = match.group(0)

    assert len(scm.CATEGORIES) == 57
    assert " disabled>" not in select_html
    for category in scm.CATEGORIES:
        assert f'value="{category.key}">' in select_html


def test_requeue_does_not_reference_capture_routes():
    """This panel moves lifecycle items (needs_review/rejected -> processing).
    It must never call a /api/capture/* route — that surface belongs to the
    live capture tool and is out of scope for this feature."""
    html = _html()

    requeue_iife = html[html.index("Requeue: Needs Review"):html.index("Default view on load")]
    assert "/api/capture/" not in requeue_iife
