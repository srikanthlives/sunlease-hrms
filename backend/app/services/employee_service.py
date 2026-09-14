import secrets
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.enums import RoleName
from app.models.models import OrgAssignment, CostAllocation, Nominee, EmploymentEpisode, Role, User


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
    """Episodes "in" Cost Center X during [start_date, end_date] - matched
    via EITHER an overlapping OrgAssignment OR an overlapping
    CostAllocation (in cost_center_id, if given - else across ALL cost
    centers). Used to answer "who was in Cost Center X during month Y" for
    the app-level Month+Cost Center filter (Employees/Attendance/Leave/
    Payroll/Compliance list scoping).

    CostAllocation is included, not just OrgAssignment, because the two
    are independent in this codebase's model (blueprint §6) - an episode
    converted straight from a recruitment Candidate
    (recruitment_service.convert_to_employee) gets a CostAllocation
    immediately but no OrgAssignment (Department is filled in later, via
    the wizard), and would otherwise vanish from every month-filtered list
    in the app until someone completed that step, despite genuinely
    existing and being assigned to a cost center. Returns distinct
    EmploymentEpisode objects (an episode could in theory have been
    reassigned/reallocated within the window - only counted once)."""
    org_query = db.query(OrgAssignment.episode_id).filter(
        OrgAssignment.effective_from <= end_date,
        (OrgAssignment.effective_to.is_(None)) | (OrgAssignment.effective_to >= start_date),
    )
    alloc_query = db.query(CostAllocation.episode_id).filter(
        CostAllocation.effective_from <= end_date,
        (CostAllocation.effective_to.is_(None)) | (CostAllocation.effective_to >= start_date),
    )
    if cost_center_id is not None:
        org_query = org_query.filter(OrgAssignment.cost_center_id == cost_center_id)
        alloc_query = alloc_query.filter(CostAllocation.cost_center_id == cost_center_id)
    episode_ids = {row[0] for row in org_query.distinct().all()} | {row[0] for row in alloc_query.distinct().all()}
    if not episode_ids:
        return []
    return db.query(EmploymentEpisode).filter(EmploymentEpisode.id.in_(episode_ids)).all()


def _generate_pin() -> str:
    return f"{secrets.randbelow(10**8):08d}"


def _employee_full_name(employee) -> str | None:
    if not employee:
        return None
    parts = [employee.first_name, employee.middle_name, employee.last_name]
    return " ".join(p for p in parts if p)


def provision_self_service_login(db: Session, episode: EmploymentEpisode) -> dict | None:
    """Creates a self-service (EMPLOYEE role) login for this episode's
    Employee if one doesn't already exist, keyed by employee_number as the
    username (blueprint §19). Returns {"username", "initial_pin"} only when
    a new login was actually created (the plaintext PIN is never stored -
    the caller must surface it once), or None if a login already existed."""
    existing = db.query(User).filter(User.employee_id == episode.employee_id).first()
    if existing:
        return None

    role = db.query(Role).filter(Role.name == RoleName.EMPLOYEE).first()
    if not role:
        return None

    pin = _generate_pin()
    user = User(
        username=episode.employee_number,
        full_name=_employee_full_name(episode.employee),
        hashed_password=hash_password(pin),
        role_id=role.id,
        employee_id=episode.employee_id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return {"username": user.username, "initial_pin": pin}


def reset_self_service_login(db: Session, episode: EmploymentEpisode) -> dict:
    """Regenerates the PIN for an existing self-service login, or
    provisions one if it's somehow missing (e.g. episode activated before
    this feature existed). Always returns the new plaintext PIN once."""
    user = db.query(User).filter(User.employee_id == episode.employee_id).first()
    if not user:
        result = provision_self_service_login(db, episode)
        if not result:
            raise ValueError("EMPLOYEE role not found - cannot provision a self-service login")
        return result

    pin = _generate_pin()
    user.hashed_password = hash_password(pin)
    user.is_active = True
    db.add(user)
    return {"username": user.username, "initial_pin": pin}


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
