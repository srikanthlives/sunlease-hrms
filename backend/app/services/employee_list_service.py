"""The Employees list, as one reusable row builder.

Lifted out of routers/employees.py's GET "" handler so the Excel export
(services/export_service.py) serves exactly the rows the list page shows,
rather than a second query that could drift from it - the same reason
Module 4's compliance aggregation reads already-computed PayslipLine
amounts instead of recomputing them.
"""
import calendar
from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.models.enums import EpisodeStatus
from app.models.models import (
    CostAllocation, CostCenter, Department, EmployeeTransfer, EmploymentEpisode, OrgAssignment, Project, User,
)
from app.services import document_service, employee_service, permission_service


def list_rows(
    db: Session, user: User, cost_center_id: int | None = None, year: int | None = None, month: int | None = None,
) -> list[dict]:
    """One dict per EmploymentEpisode the caller is allowed to see. Cost
    Center scoping is applied per row (not as a query filter) because the
    Cost Center shown is resolved from the open OrgAssignment, falling back
    to the open CostAllocation."""
    query = (
        db.query(EmploymentEpisode)
        .options(
            joinedload(EmploymentEpisode.employee),
            joinedload(EmploymentEpisode.employee_category),
            joinedload(EmploymentEpisode.employee_type),
            joinedload(EmploymentEpisode.designation),
            joinedload(EmploymentEpisode.work_location),
        )
        .order_by(EmploymentEpisode.id.desc())
    )

    # year+month given: scope to episodes that had an OrgAssignment
    # overlapping that month (optionally restricted to cost_center_id).
    # Otherwise (params omitted): unchanged Phase 1 behavior - all episodes,
    # cost_center/department shown from whatever assignment is CURRENTLY open.
    allowed_episode_ids = None
    if year is not None and month is not None:
        _, last_day = calendar.monthrange(year, month)
        month_start, month_end = date(year, month, 1), date(year, month, last_day)
        allowed_episode_ids = {
            ep.id for ep in employee_service.episodes_in_cost_center_during(db, cost_center_id, month_start, month_end)
        }
        query = query.filter(EmploymentEpisode.id.in_(allowed_episode_ids)) if allowed_episode_ids else query.filter(False)

    episodes = query.all()

    # Bulk-fetch the currently-open assignment per episode (and the Cost
    # Center/Department names it points at) instead of one query per row.
    # Fall back to an open CostAllocation for the Cost Center column when
    # there's no OrgAssignment yet (e.g. an episode just converted from a
    # recruitment Candidate, which gets a CostAllocation immediately but
    # no OrgAssignment/Department until the wizard's Org Assignment step
    # - see employee_service.episodes_in_cost_center_during).
    open_assignments = db.query(OrgAssignment).filter(OrgAssignment.effective_to.is_(None)).all()
    assignment_by_episode = {a.episode_id: a for a in open_assignments}
    open_allocations = db.query(CostAllocation).filter(CostAllocation.effective_to.is_(None)).all()
    allocation_by_episode: dict[int, CostAllocation] = {}
    for alloc in open_allocations:
        allocation_by_episode.setdefault(alloc.episode_id, alloc)
    # A Separated stint's assignments are closed at exit - show (and scope
    # by) the Cost Center/Department it last had instead of blanks.
    separated_ids = [e.id for e in episodes if e.status == EpisodeStatus.SEPARATED and e.id not in assignment_by_episode]
    if separated_ids:
        for a in db.query(OrgAssignment).filter(OrgAssignment.episode_id.in_(separated_ids)).order_by(OrgAssignment.effective_from, OrgAssignment.id).all():
            assignment_by_episode[a.episode_id] = a
        for al in db.query(CostAllocation).filter(CostAllocation.episode_id.in_(separated_ids)).order_by(CostAllocation.effective_from, CostAllocation.id).all():
            allocation_by_episode[al.episode_id] = al
    cost_centers = {c.id: c.name for c in db.query(CostCenter.id, CostCenter.name).all()}
    departments = {d.id: d.name for d in db.query(Department.id, Department.name).all()}
    project_names = {p.id: p.name for p in db.query(Project.id, Project.name).all()}

    transferred_in_ids = {t.to_episode_id for t in db.query(EmployeeTransfer).filter(EmployeeTransfer.status != "CANCELLED").all() if t.to_episode_id}

    rows = []
    for e in episodes:
        assignment = assignment_by_episode.get(e.id)
        cc_id = assignment.cost_center_id if assignment else None
        if cc_id is None:
            allocation = allocation_by_episode.get(e.id)
            cc_id = allocation.cost_center_id if allocation else None
        if not permission_service.can_see_cost_center(db, user, cc_id):
            continue
        # When a plain cost_center_id filter is given without year/month,
        # fall back to filtering on the currently-open assignment (no
        # overlap window to resolve against).
        if cost_center_id is not None and year is None and month is None and cc_id != cost_center_id:
            continue
        mandatory_docs = [d for d in document_service.resolve_required_documents(db, e) if d["is_mandatory"]]
        rows.append({
            "episode_id": e.id,
            "employee_id": e.employee_id,
            "employee_number": e.employee_number,
            "first_name": e.employee.first_name,
            "last_name": e.employee.last_name,
            "gender": e.employee.gender,
            "mobile_number": e.employee.mobile_number,
            "official_email": e.employee.official_email,
            "designation": e.designation.name if e.designation else None,
            "employment_type": e.employee_type.name if e.employee_type else None,
            "employee_category": e.employee_category.name if e.employee_category else None,
            "date_of_joining": e.date_of_joining,
            "separation_date": e.separation_date,
            "rejoined": e.previous_episode_id is not None,
            "origin": ("TRANSFER" if e.id in transferred_in_ids else "REJOIN") if e.previous_episode_id is not None else None,
            "work_location": e.work_location.name if e.work_location else None,
            "cost_center": cost_centers.get(cc_id),
            "department": departments.get(assignment.department_id) if assignment else None,
            "project": project_names.get(assignment.project_id) if assignment and assignment.project_id else None,
            "documents_uploaded_count": len(e.documents),
            "documents_all_mandatory_uploaded": bool(mandatory_docs) and all(d["uploaded"] for d in mandatory_docs),
            "father_husband_name": e.employee.father_husband_name,
            "date_of_birth": e.employee.date_of_birth,
            "personal_email": e.employee.personal_email,
            "alternate_mobile_number": e.employee.alternate_mobile_number,
            "confirmation_date": e.confirmation_date,
            "shift_group": e.shift_group,
            "application_reference_number": e.application_reference_number,
            "status": e.status,
        })
    return rows
