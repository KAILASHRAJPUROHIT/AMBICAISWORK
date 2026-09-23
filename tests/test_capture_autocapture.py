from pathlib import Path


BASE = Path(__file__).resolve().parents[1]


def test_capture_page_has_opt_in_local_assist_and_manual_override():
    source = (BASE / "templates" / "capture.html").read_text(encoding="utf-8")

    assert 'id="camera-analysis-canvas"' in source
    assert 'id="camera-auto-enabled" type="checkbox"' in source
    assert "Assist mode · manual shutter" in source
    assert "localStorage.getItem('aradhana_auto_capture_v1') || 'auto'" in source
    assert "cameraShutter.addEventListener('click', () => captureOptimizedPhoto('manual', null))" in source
    assert "new Worker('/static/capture_quality_worker.js?v='" in source


def test_autocapture_requires_temporal_quality_and_tag_consensus():
    source = (BASE / "templates" / "capture.html").read_text(encoding="utf-8")

    assert "const neededFrames = isTag ? 1 : 2" in source
    assert "_qualityTagHistory.length >= 2" in source
    assert "if (!cameraAutoEnabled.checked) return" in source
    assert "ready && !_qualityAutoFired && cameraAutoEnabled.checked" in source
    assert "normalisedTagCode(decoded) !== normalisedTagCode(expectedTag)" in source
    assert "Saving maximum-resolution still" in source
    assert "validateAutomaticCapture(blob, kind, expectedTag)" in source
    assert "Date.now() + 1500" in source


def test_auto_burst_saves_a_native_full_resolution_still():
    source = (BASE / "templates" / "capture.html").read_text(encoding="utf-8")

    assert "const burstCount = 5" in source
    assert "const burstSpacingMs = 200" in source
    assert "createVideoAnalysisBitmap(720, null)" in source
    assert "const fullBlob = await captureStillBlob()" in source
    assert "validateAutomaticCapture(fullBlob, kind, null)" in source
    assert "return {blob: fullBlob" in source


def test_android_main_lens_is_selected_by_device_id_and_defaults_to_one_x():
    source = (BASE / "templates" / "capture.html").read_text(encoding="utf-8")

    assert "navigator.mediaDevices.enumerateDevices()" in source
    assert "baseVideoConstraints.deviceId = {exact: deviceId}" in source
    assert "cameraDevicePreferenceKey()" in source
    assert "automatic main-lens selection" in source
    assert "ultra[ -]?wide|tele|periscope|macro|depth" in source
    assert "nothing: {front: 1, tag: 1}" in source
    assert "redmi: {front: 1, tag: 1}" in source
    assert 'id="camera-recheck-lens"' in source


def test_live_gate_uses_low_rate_detection_and_target_detail_confirmation():
    source = (BASE / "templates" / "capture.html").read_text(encoding="utf-8")

    assert "now - _qualityLastAnalysisAt >= 200" in source
    assert "createVideoAnalysisBitmap(360, null)" in source
    assert "createVideoAnalysisBitmap(720, result.goldBounds)" in source
    assert "detailSharpnessConfirmed: true" in source
    assert "result.detailSharpnessConfirmed === true" in source
    assert "stopQualityAnalysis();" in source


def test_quality_worker_is_local_and_checks_multiple_failure_modes():
    source = (BASE / "static" / "capture_quality_worker.js").read_text(encoding="utf-8")

    assert "new OffscreenCanvas" in source
    assert "contiguousFastCorner" in source
    assert "occupiedCells" in source
    assert "lapVariance" in source
    assert "clippedRatio" in source
    assert "qualityInsideBounds" in source
    assert "let analysisCanvas = null" in source
    assert "const maximum = finalFrame ? 720 : 360" in source
    assert "const selected = support ?" in source
    assert "motion !== null" in source
    assert "self.postMessage" in source
    assert "fetch(" not in source
