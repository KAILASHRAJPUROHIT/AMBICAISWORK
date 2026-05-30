from backend.prime_robot.checkpoint_manager import CheckpointManager

def test_checkpoint_initialization():
    manager = CheckpointManager()
    assert manager.checkpoint is None
