from backend.prime_robot.idle_monitor import IdleMonitor

def test_idle_monitor_initialization():
    monitor = IdleMonitor()
    assert monitor.is_active is False
