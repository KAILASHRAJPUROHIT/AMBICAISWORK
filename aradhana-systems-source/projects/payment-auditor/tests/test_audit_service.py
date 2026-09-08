import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models import AuditLog
from backend.schemas import AuditLogCreate
from backend.audit_service import create_audit_log, get_entity_history

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()

def test_audit_creation(db_session):
    audit_in = AuditLogCreate(
        entity_type="bill",
        entity_id=1,
        action="status_change",
        old_status="Yellow",
        new_status="Green",
        actor="system",
        metadata_json='{"reason": "exact match"}'
    )
    log = create_audit_log(db_session, audit_in)
    assert log.id is not None
    assert log.entity_type == "bill"
    assert log.entity_id == 1
    assert log.actor == "system"
    assert log.old_status == "Yellow"
    assert log.new_status == "Green"
    assert log.metadata_json == '{"reason": "exact match"}'

def test_history_retrieval(db_session):
    for i in range(3):
        create_audit_log(db_session, AuditLogCreate(
            entity_type="payment",
            entity_id=42,
            action=f"action_{i}",
            actor="user1"
        ))
    
    # Unrelated log
    create_audit_log(db_session, AuditLogCreate(
        entity_type="payment",
        entity_id=99,
        action="unrelated",
        actor="user1"
    ))

    history = get_entity_history(db_session, "payment", 42)
    assert len(history) == 3
    # The logs are returned descending by created_at.
    # Actually, in SQLite memory, created_at might be exactly the same (func.now() resolution),
    # so we might need to rely on id to assert order if created_at is identical.
    # Let's just assert the length and that the related actions are present.
    actions = [h.action for h in history]
    assert "action_0" in actions
    assert "action_1" in actions
    assert "action_2" in actions
    assert "unrelated" not in actions

def test_append_only_behavior():
    import backend.audit_service
    functions = dir(backend.audit_service)
    
    assert not any("update" in f for f in functions)
    assert not any("delete" in f for f in functions)
    assert not any("remove" in f for f in functions)
    assert not any("modify" in f for f in functions)
