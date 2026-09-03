from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.models import OrgAssignment, CostAllocation, Nominee


def add_org_assignment(db: Session, episode_id: int, data: dict) -> OrgAssignment:
    """Closes any currently-open assignment for this episode, then inserts
    the new one. Enforces blueprint §21: an employee has only one active
    Department at a time."""
    open_assignment = (
        db.query(OrgAssignment)
        .filter(OrgAssignment.episode_id == episode_id, OrgAssignment.effective_to.is_(None))
        .first()
    )
    new_from = data["effective_from"]
    if open_assignment and open_assignment.effective_from < new_from:
        open_assignment.effective_to = new_from - timedelta(days=1)
        db.add(open_assignment)

    assignment = OrgAssignment(episode_id=episode_id, **data)
    db.add(assignment)
    return assignment


def add_cost_allocation(db: Session, episode_id: int, data: dict) -> CostAllocation:
    allocation = CostAllocation(episode_id=episode_id, **data)
    db.add(allocation)
    return allocation


def active_allocation_total(db: Session, episode_id: int) -> float:
    rows = (
        db.query(CostAllocation)
        .filter(CostAllocation.episode_id == episode_id, CostAllocation.effective_to.is_(None))
        .all()
    )
    return sum(r.percentage for r in rows)


def nominee_total(db: Session, episode_id: int, nomination_type: str | None) -> float:
    """Nomination percentage pools are independent per type (PF/Gratuity/
    Insurance/Other) - a Provident Fund nomination totalling 100% across
    its nominees doesn't constrain the Gratuity nomination's own 100%."""
    rows = (
        db.query(Nominee)
        .filter(Nominee.episode_id == episode_id, Nominee.nomination_type == nomination_type)
        .all()
    )
    return sum(r.percentage or 0 for r in rows)
