from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.models import OrgAssignment, CostAllocation, Nominee, EmploymentEpisode


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


def episodes_in_cost_center_during(db: Session, cost_center_id: int | None, start_date: date, end_date: date) -> list[EmploymentEpisode]:
    """Episodes with an OrgAssignment (in cost_center_id, if given - else
    across ALL cost centers) overlapping [start_date, end_date]. Used to
    answer "who was in Cost Center X during month Y" for the app-level
    Month+Cost Center filter (Employees/Attendance/Leave list scoping).
    Returns distinct EmploymentEpisode objects (an episode could in theory
    have been reassigned within the window - only counted once)."""
    query = db.query(OrgAssignment.episode_id).filter(
        OrgAssignment.effective_from <= end_date,
        (OrgAssignment.effective_to.is_(None)) | (OrgAssignment.effective_to >= start_date),
    )
    if cost_center_id is not None:
        query = query.filter(OrgAssignment.cost_center_id == cost_center_id)
    episode_ids = {row[0] for row in query.distinct().all()}
    if not episode_ids:
        return []
    return db.query(EmploymentEpisode).filter(EmploymentEpisode.id.in_(episode_ids)).all()


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
