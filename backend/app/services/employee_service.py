import secrets
import os
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.enums import EpisodeStatus, RoleName
from app.models.models import (
    Address, BankAccount, CostAllocation, Department, Dependent, DocumentMeta, DrivingLicenceDetail, Employee,
    EmploymentEpisode, LeaveBalance, Nominee, OrgAssignment, Project, Role, StatutoryInfo, User,
)


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
        # The login name is the employee number; a transfer to another Cost
        # Center gives a new number, so keep the username in step with it.
        if existing.username != episode.employee_number and not db.query(User).filter(
            User.username == episode.employee_number, User.id != existing.id,
        ).first():
            existing.username = episode.employee_number
            db.add(existing)
        if not existing.is_active:
            # Disabled at the employee's earlier exit (disable_self_service_login)
            # - re-enable on rejoin with a fresh one-time PIN.
            pin = _generate_pin()
            existing.hashed_password = hash_password(pin)
            existing.is_active = True
            db.add(existing)
            return {"username": existing.username, "initial_pin": pin}
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


def find_episode_by_number(db: Session, employee_number: str) -> EmploymentEpisode | None:
    """An employee number can appear on several stints of a rejoiner (only
    one non-Separated at a time - see uq_active_employee_number). Returns
    the live stint if there is one, else the most recent one."""
    rows = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == employee_number).order_by(EmploymentEpisode.id.desc()).all()
    for r in rows:
        if r.status != EpisodeStatus.SEPARATED:
            return r
    return rows[0] if rows else None


def close_assignments_at_exit(db: Session, episode: EmploymentEpisode) -> None:
    """A stint's Cost Center/Department assignments and cost allocations end
    on its exit date, so the person stops appearing in that Cost Center's
    later months (the rows themselves stay as history)."""
    end = episode.separation_date or date.today()
    for model in (OrgAssignment, CostAllocation):
        for row in db.query(model).filter(model.episode_id == episode.id, model.effective_to.is_(None)).all():
            row.effective_to = max(row.effective_from, end)
            db.add(row)


def disable_self_service_login(db: Session, employee_id: int) -> None:
    for user in db.query(User).filter(User.employee_id == employee_id).all():
        user.is_active = False
        db.add(user)


def last_cost_center_id(db: Session, episode_id: int) -> int | None:
    """Current Cost Center if one is open, else the most recent one the
    stint ever had (a Separated stint's assignments are closed)."""
    row = (
        db.query(OrgAssignment).filter(OrgAssignment.episode_id == episode_id)
        .order_by(OrgAssignment.effective_to.is_(None).desc(), OrgAssignment.effective_from.desc(), OrgAssignment.id.desc()).first()
    )
    if row:
        return row.cost_center_id
    alloc = (
        db.query(CostAllocation).filter(CostAllocation.episode_id == episode_id)
        .order_by(CostAllocation.effective_to.is_(None).desc(), CostAllocation.effective_from.desc(), CostAllocation.id.desc()).first()
    )
    return alloc.cost_center_id if alloc else None


def home_cost_center_id(db: Session, episode_id: int) -> int | None:
    """The Cost Center a stint belongs to: its open Cost Center/Department
    assignment, else (a draft converted from a candidate, which only has a
    cost allocation so far) its open cost allocation."""
    a = db.query(OrgAssignment).filter(OrgAssignment.episode_id == episode_id, OrgAssignment.effective_to.is_(None)).first()
    if a:
        return a.cost_center_id
    al = db.query(CostAllocation).filter(CostAllocation.episode_id == episode_id, CostAllocation.effective_to.is_(None)).first()
    return al.cost_center_id if al else None


def guard_cost_center_change(db: Session, episode: EmploymentEpisode, new_cost_center_id: int) -> None:
    """Project/Department can change freely inside a Cost Center, but the
    Cost Center itself is fixed once a stint is live - moving to another one
    is a Transfer (exit in the old, entry in the new). A rejoin/transfer
    draft has its Cost Center fixed from the start."""
    home = home_cost_center_id(db, episode.id)
    if home is None or home == new_cost_center_id:
        return
    live = episode.status not in (EpisodeStatus.DRAFT, EpisodeStatus.PENDING_APPROVAL)
    if live or episode.previous_episode_id is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "A Cost Center change is a Transfer - use the Transfer action (exit from the current Cost Center, entry into the new one)",
        )


def guard_allocation_cost_center(db: Session, episode: EmploymentEpisode, cost_center_id: int) -> None:
    """Each Cost Center's employment is kept separate - cost is not split
    across Cost Centers (Projects inside the Cost Center can still be split)."""
    home = home_cost_center_id(db, episode.id)
    if home is not None and cost_center_id != home:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Cost allocation must stay within the employee's own Cost Center - employment in each Cost Center is kept separate (use Transfer to move)",
        )


def number_for_cost_center(db: Session, employee_id: int, cost_center_id: int) -> tuple[str, EmploymentEpisode] | None:
    """The employee number this person held the last time they served in
    the given Cost Center, if ever - a number identifies a person within a
    Cost Center, so coming back reuses it."""
    for e in db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_id == employee_id).order_by(EmploymentEpisode.id.desc()).all():
        if last_cost_center_id(db, e.id) == cost_center_id:
            return e.employee_number, e
    return None


def check_number_available(db: Session, number: str, employee_id: int, cost_center_id: int | None, exclude_episode_id: int | None = None) -> None:
    """409 unless `number` can be used by this person in this Cost Center:
    never on another person's record, never while live on another record,
    and (for this person's own earlier records) only in the Cost Center it
    was originally issued for."""
    q = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == number)
    if exclude_episode_id:
        q = q.filter(EmploymentEpisode.id != exclude_episode_id)
    for e in q.all():
        if e.employee_id != employee_id or e.status != EpisodeStatus.SEPARATED:
            raise HTTPException(status.HTTP_409_CONFLICT, "Employee Number already in use")
        if cost_center_id is not None and last_cost_center_id(db, e.id) != cost_center_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "This employee number was issued for a different Cost Center - use a new number")


def purge_draft_episode(db: Session, episode: EmploymentEpisode) -> None:
    """Hard-deletes a DRAFT stint and everything hanging off it (its Employee
    row too if it was that person's only stint). Caller commits."""
    from app.services import document_service  # local: avoids an import cycle

    for document in db.query(DocumentMeta).filter(DocumentMeta.episode_id == episode.id).all():
        try:
            path = document_service.resolve_file_path(document)
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    db.query(DocumentMeta).filter(DocumentMeta.episode_id == episode.id).delete(synchronize_session=False)
    for model in (OrgAssignment, CostAllocation, StatutoryInfo, BankAccount, Dependent, Nominee, DrivingLicenceDetail):
        db.query(model).filter(model.episode_id == episode.id).delete(synchronize_session=False)
    employee_id = episode.employee_id
    db.query(EmploymentEpisode).filter(EmploymentEpisode.id == episode.id).delete(synchronize_session=False)
    if db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_id == employee_id).count() == 0:
        db.query(Address).filter(Address.employee_id == employee_id).delete(synchronize_session=False)
        db.query(Employee).filter(Employee.id == employee_id).delete(synchronize_session=False)


def create_new_stint(
    db: Session, prior: EmploymentEpisode, date_of_joining: date, cost_center_id: int, project_id: int, department_id: int,
    employee_number: str | None, continuous_service: bool,
) -> EmploymentEpisode:
    """Starts a new DRAFT stint for an existing person in `cost_center_id`
    (shared by Rejoin and Transfer). Number: the one they held in that Cost
    Center before if any, else `employee_number` (required, must be free).
    Goes through the normal wizard/approval afterwards.

    Carried as editable starting points: employment info, latest bank and
    statutory record (UAN/ESI numbers), dependents, nominees, driving
    licence. The Cost Center/Department assignment and 100% cost allocation
    are created for the chosen Cost Center. Salary structure, attendance,
    payroll and documents start fresh. continuous_service (INTERNAL transfer
    only) additionally carries service start, confirmation date and this
    year's leave usage/opening so entitlements and gratuity service continue."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or project.cost_center_id != cost_center_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Project does not belong to the selected Cost Center")
    if not db.query(Department).filter(Department.id == department_id, Department.is_active.is_(True)).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Department not found")

    reuse = number_for_cost_center(db, prior.employee_id, cost_center_id)
    if reuse:
        number = reuse[0]
    else:
        number = (employee_number or "").strip()
        if not number:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A new Employee Number is required for this Cost Center")
    check_number_available(db, number, prior.employee_id, cost_center_id)

    new = EmploymentEpisode(
        employee_id=prior.employee_id, employee_number=number, status=EpisodeStatus.DRAFT,
        date_of_joining=date_of_joining, previous_episode_id=prior.id,
        employment_type_id=prior.employment_type_id, employee_category_id=prior.employee_category_id,
        designation_id=prior.designation_id, work_location_id=None, shift_group=prior.shift_group,
    )
    if continuous_service:
        new.service_start_date = prior.service_start_date or prior.date_of_joining
        new.confirmation_date = prior.confirmation_date
    db.add(new)
    db.flush()

    db.add(OrgAssignment(episode_id=new.id, cost_center_id=cost_center_id, department_id=department_id, project_id=project_id, effective_from=date_of_joining))
    db.add(CostAllocation(episode_id=new.id, cost_center_id=cost_center_id, project_id=project_id, percentage=100, effective_from=date_of_joining))

    def newest(model):
        return db.query(model).filter(model.episode_id == prior.id).order_by(model.effective_from.desc(), model.id.desc()).first()

    bank = newest(BankAccount)
    if bank:
        db.add(BankAccount(
            episode_id=new.id, bank_name=bank.bank_name, branch=bank.branch, account_number=bank.account_number, ifsc=bank.ifsc,
            account_holder_name=bank.account_holder_name, account_type=bank.account_type, payment_mode=bank.payment_mode,
            is_primary=bank.is_primary, effective_from=date_of_joining,
        ))
    stat = newest(StatutoryInfo)
    if stat:
        db.add(StatutoryInfo(
            episode_id=new.id, pf_eligible=stat.pf_eligible, pf_name_on_file=stat.pf_name_on_file, uan=stat.uan,
            pf_effective_date=date_of_joining if stat.pf_eligible else None,
            esi_eligible=stat.esi_eligible, esi_name_on_file=stat.esi_name_on_file, esi_number=stat.esi_number,
            esi_mediclaim_number=stat.esi_mediclaim_number, esi_effective_date=date_of_joining if stat.esi_eligible else None,
            pt_eligible=stat.pt_eligible, gratuity_eligible=stat.gratuity_eligible, effective_from=date_of_joining,
        ))
    for d in db.query(Dependent).filter(Dependent.episode_id == prior.id).all():
        db.add(Dependent(episode_id=new.id, name=d.name, relationship_type=d.relationship_type, date_of_birth=d.date_of_birth))
    for n in db.query(Nominee).filter(Nominee.episode_id == prior.id, Nominee.effective_to.is_(None)).all():
        db.add(Nominee(
            episode_id=new.id, name=n.name, relationship_type=n.relationship_type, date_of_birth=n.date_of_birth, address=n.address,
            mobile=n.mobile, percentage=n.percentage, nomination_type=n.nomination_type, effective_from=date_of_joining,
        ))
    dl = db.query(DrivingLicenceDetail).filter(DrivingLicenceDetail.episode_id == prior.id).first()
    if dl:
        db.add(DrivingLicenceDetail(
            episode_id=new.id, licence_number=dl.licence_number, badge_number=dl.badge_number, vehicle_class=dl.vehicle_class,
            issuing_authority=dl.issuing_authority, issue_date=dl.issue_date, expiry_date=dl.expiry_date,
        ))
    if continuous_service:
        for b in db.query(LeaveBalance).filter(LeaveBalance.episode_id == prior.id, LeaveBalance.year == date_of_joining.year).all():
            db.add(LeaveBalance(
                episode_id=new.id, leave_type_id=b.leave_type_id, year=b.year,
                opening_balance=b.opening_balance, accrued=0, used=b.used, adjusted=b.adjusted,
            ))
    db.flush()
    return new


def create_rejoin_episode(
    db: Session, prior: EmploymentEpisode, date_of_joining: date, cost_center_id: int, project_id: int, department_id: int,
    employee_number: str | None, user: User,
) -> EmploymentEpisode:
    """Re-hires a fully Separated person (after a real exit - separate
    service, nothing carries over) into the chosen Cost Center."""
    if prior.status != EpisodeStatus.SEPARATED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a fully Separated employee can rejoin")
    if db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_id == prior.employee_id, EmploymentEpisode.status != EpisodeStatus.SEPARATED).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This employee already has a current or pending employment record")
    latest = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_id == prior.employee_id).order_by(EmploymentEpisode.id.desc()).first()
    if latest.id != prior.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rejoin from this employee's most recent employment record")
    if prior.separation_date and date_of_joining <= prior.separation_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rejoining date must be after the previous exit date")
    return create_new_stint(db, prior, date_of_joining, cost_center_id, project_id, department_id, employee_number, continuous_service=False)
