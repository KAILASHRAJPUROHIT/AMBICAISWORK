from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_service_ports_and_isolation_are_hardwalled():
    script = (ROOT / "scripts" / "aradhana_service_control.ps1").read_text(encoding="utf-8")

    assert 'Start-Environment "production" 8000 5173 "production" $false' in script
    assert 'Start-Environment "dev" 8010 5183 "dev" $true' in script
    assert "Test-ManagedListener $BackendPort $backendPid $true" in script
    assert "Test-ManagedListener $FrontendPort $frontendPid $false" in script
    assert "Found healthy unmanaged Aradhana backend" in script
    assert "Found healthy unmanaged Aradhana frontend" in script
    assert "unmanaged and unhealthy/unknown" in script
    assert "--strictPort" in script
    assert "ARADHANA_DB_PATH" in script
    assert "aradhana_dev_isolated.db" in script
    assert "data\\dev" in script
    assert "INVOICE_SHARE_PATH" in script
    assert "INVOICE_SHARE_PATH_PRIMARY" in script
    assert "INVOICE_SHARE_PATH_FALLBACK" in script
    assert "BACKEND_PORT" in script
    assert "FRONTEND_PORT" in script


def test_batch_launchers_delegate_to_single_controller():
    launchers = {
        "start_aradhana_lan_server.bat": "start-prod",
        "stop_production_server.bat": "stop-prod",
        "status_production_server.bat": "status-prod",
        "start_dev_instance.bat": "start-dev",
        "stop_dev_instance.bat": "stop-dev",
    }
    for filename, mode in launchers.items():
        content = (ROOT / filename).read_text(encoding="utf-8")
        assert "scripts\\aradhana_service_control.ps1" in content
        assert mode in content
