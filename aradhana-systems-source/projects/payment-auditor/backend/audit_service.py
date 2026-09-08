from sqlalchemy.orm import Session
from backend.models import AuditLog
from backend.schemas import AuditLogCreate
from typing import List

def create_audit_log(db: Session, audit_in: AuditLogCreate) -> AuditLog:
    db_log = AuditLog(
        entity_type=audit_in.entity_type,
        entity_id=audit_in.entity_id,
        action=audit_in.action,
        old_status=audit_in.old_status,
        new_status=audit_in.new_status,
        actor=audit_in.actor,
        metadata_json=audit_in.metadata_json
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log

def get_entity_history(db: Session, entity_type: str, entity_id: int) -> List[AuditLog]:
    return db.query(AuditLog).filter(
        AuditLog.entity_type == entity_type,
        AuditLog.entity_id == entity_id
    ).order_by(AuditLog.created_at.desc()).all()
