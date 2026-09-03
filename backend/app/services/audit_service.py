from sqlalchemy.orm import Session

from app.models.models import AuditLog, User


def record(db: Session, entity: str, record_id, action: str, actor: User, old_value=None, new_value=None):
    """Writes one append-only audit row (blueprint §20). Caller still owns
    the commit - this only adds to the session."""
    db.add(AuditLog(
        user_id=actor.id if actor else None,
        username=actor.username if actor else None,
        role=actor.role.name if actor and actor.role else None,
        action=action,
        entity=entity,
        record_id=str(record_id),
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
    ))
