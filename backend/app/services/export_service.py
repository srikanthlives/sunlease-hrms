"""Configurable Excel export of the Employees and Candidates lists.

The rows are NOT queried here. Both entities' list endpoints already build
exactly the rows their list page shows, in services/employee_list_service.py
and services/candidate_list_service.py, and this module consumes those -
same reason Module 4's compliance aggregation reads already-computed
PayslipLine amounts instead of recomputing them. What this module adds on
top is the *pattern*: which columns, in which order, sorted how, filtered to
which subset.

Sensitive employee columns (Aadhaar/PAN/UAN/ESI/bank account/IFSC) are not
part of the list rows at all, so they are fetched separately and only for a
caller holding employee.sensitive.view - the same gate
permission_service.mask_sensitive_fields applies to the profile page. They
are left out of the offered catalog entirely for anyone else, so an export
can never become a way around the masking.

Candidate Aadhaar/PAN/licence numbers deliberately follow the Candidates
list's own policy (shown to anyone with recruitment.view, and searchable
there) rather than a stricter one invented here.
"""
import datetime as dt
from typing import Any

from fastapi import HTTPException, status
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.models.enums import Permission
from app.models.models import BankAccount, ExportTemplate, StatutoryInfo, User
from app.services import candidate_list_service, employee_list_service, permission_service

EMPLOYEE = "EMPLOYEE"
CANDIDATE = "CANDIDATE"
ENTITIES = (EMPLOYEE, CANDIDATE)
PREVIEW_ROWS = 25

# key, label, group, sensitive. `key` is the field name on the list row
# (or, for a sensitive one, the name resolved by _sensitive_values).
EMPLOYEE_COLUMNS: list[dict] = [
    {"key": "employee_number", "label": "Employee No.", "group": "Employment"},
    {"key": "first_name", "label": "First Name", "group": "Personal"},
    {"key": "last_name", "label": "Last Name", "group": "Personal"},
    {"key": "father_husband_name", "label": "Father / Husband Name", "group": "Personal"},
    {"key": "gender", "label": "Gender", "group": "Personal"},
    {"key": "date_of_birth", "label": "Date of Birth", "group": "Personal"},
    {"key": "mobile_number", "label": "Mobile", "group": "Contact"},
    {"key": "alternate_mobile_number", "label": "Alternate Mobile", "group": "Contact"},
    {"key": "official_email", "label": "Official Email", "group": "Contact"},
    {"key": "personal_email", "label": "Personal Email", "group": "Contact"},
    {"key": "designation", "label": "Designation", "group": "Employment"},
    {"key": "employment_type", "label": "Employment Type", "group": "Employment"},
    {"key": "employee_category", "label": "Employee Category", "group": "Employment"},
    {"key": "cost_center", "label": "Cost Center", "group": "Organization"},
    {"key": "department", "label": "Department", "group": "Organization"},
    {"key": "project", "label": "Project", "group": "Organization"},
    {"key": "work_location", "label": "Work Location", "group": "Organization"},
    {"key": "shift_group", "label": "Shift Group", "group": "Employment"},
    {"key": "date_of_joining", "label": "Date of Joining", "group": "Employment"},
    {"key": "confirmation_date", "label": "Confirmation Date", "group": "Employment"},
    {"key": "status", "label": "Status", "group": "Employment"},
    {"key": "separation_date", "label": "Separation Date", "group": "Employment"},
    {"key": "rejoined", "label": "Rejoined / Transferred In", "group": "Employment"},
    {"key": "origin", "label": "Origin (Rejoin / Transfer)", "group": "Employment"},
    {"key": "application_reference_number", "label": "Application Reference No.", "group": "Employment"},
    {"key": "documents_uploaded_count", "label": "Documents Uploaded", "group": "Documents"},
    {"key": "documents_all_mandatory_uploaded", "label": "All Mandatory Documents", "group": "Documents"},
    # Sensitive - offered only with employee.sensitive.view.
    {"key": "aadhaar", "label": "Aadhaar", "group": "Statutory", "sensitive": True},
    {"key": "pan", "label": "PAN", "group": "Statutory", "sensitive": True},
    {"key": "uan", "label": "UAN / PF Member ID", "group": "Statutory", "sensitive": True},
    {"key": "esi_number", "label": "ESI Number", "group": "Statutory", "sensitive": True},
    {"key": "pf_eligible", "label": "PF Eligible", "group": "Statutory", "sensitive": True},
    {"key": "esi_eligible", "label": "ESI Eligible", "group": "Statutory", "sensitive": True},
    {"key": "bank_name", "label": "Bank Name", "group": "Bank", "sensitive": True},
    {"key": "bank_branch", "label": "Bank Branch", "group": "Bank", "sensitive": True},
    {"key": "account_number", "label": "Bank Account No.", "group": "Bank", "sensitive": True},
    {"key": "ifsc", "label": "IFSC", "group": "Bank", "sensitive": True},
]

CANDIDATE_COLUMNS: list[dict] = [
    {"key": "reference_number", "label": "Reference No.", "group": "Application"},
    {"key": "first_name", "label": "First Name", "group": "Personal"},
    {"key": "last_name", "label": "Last Name", "group": "Personal"},
    {"key": "gender", "label": "Gender", "group": "Personal"},
    {"key": "date_of_birth", "label": "Date of Birth", "group": "Personal"},
    {"key": "mobile_number", "label": "Mobile", "group": "Contact"},
    {"key": "alternate_mobile_number", "label": "Alternate Mobile", "group": "Contact"},
    {"key": "personal_email", "label": "Personal Email", "group": "Contact"},
    {"key": "designation_name", "label": "Applied Designation", "group": "Application"},
    {"key": "applied_employee_category_name", "label": "Applied Employee Category", "group": "Application"},
    {"key": "cost_center_name", "label": "Cost Center", "group": "Application"},
    {"key": "applied_project_name", "label": "Project", "group": "Application"},
    {"key": "applied_date", "label": "Applied Date", "group": "Application"},
    {"key": "status", "label": "Status", "group": "Application"},
    {"key": "interest_status", "label": "Interest", "group": "Application"},
    {"key": "not_interested_date", "label": "Not Interested Date", "group": "Application"},
    {"key": "source", "label": "Source", "group": "Application"},
    {"key": "educational_qualification", "label": "Qualification", "group": "Background"},
    {"key": "total_experience_years", "label": "Experience (Years)", "group": "Background"},
    {"key": "current_designation", "label": "Current Designation", "group": "Background"},
    {"key": "current_company_name", "label": "Current Company", "group": "Background"},
    {"key": "aadhaar", "label": "Aadhaar", "group": "Identity"},
    {"key": "pan", "label": "PAN", "group": "Identity"},
    {"key": "dl_licence_number", "label": "Driving Licence No.", "group": "Identity"},
    {"key": "documents_uploaded_count", "label": "Documents Uploaded", "group": "Documents"},
    {"key": "documents_all_mandatory_uploaded", "label": "All Mandatory Documents", "group": "Documents"},
    {"key": "tests_recorded_count", "label": "Tests Recorded", "group": "Tests"},
    {"key": "tests_total_count", "label": "Tests Applicable", "group": "Tests"},
    {"key": "tests_all_mandatory_passed", "label": "All Mandatory Tests Passed", "group": "Tests"},
    {"key": "remarks", "label": "Remarks", "group": "Application"},
]

DEFAULT_COLUMNS = {
    EMPLOYEE: ["employee_number", "first_name", "last_name", "designation", "cost_center", "department", "date_of_joining", "status"],
    CANDIDATE: ["reference_number", "first_name", "last_name", "designation_name", "cost_center_name", "applied_date", "status"],
}

# The filters each list page offers, mirrored so a server-side export can
# reproduce what the operator is looking at on screen.
FILTER_KEYS = {
    EMPLOYEE: ("search", "status", "cost_center", "department", "employment_type", "employee_category"),
    CANDIDATE: ("search", "status", "interest_status", "cost_center_id", "applied_project_id", "applied_employee_category_id"),
}


def check_entity(entity: str) -> str:
    if entity not in ENTITIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Entity must be one of {', '.join(ENTITIES)}")
    return entity


def columns_for(db: Session, user: User, entity: str) -> list[dict]:
    """The catalog the wizard offers. Sensitive employee columns are absent
    (not merely disabled) without employee.sensitive.view, so they can never
    be requested by name either - see _resolve_columns."""
    catalog = EMPLOYEE_COLUMNS if entity == EMPLOYEE else CANDIDATE_COLUMNS
    allowed = entity != EMPLOYEE or permission_service.has_permission(db, user, Permission.EMPLOYEE_SENSITIVE_VIEW)
    return [
        {"key": c["key"], "label": c["label"], "group": c["group"], "sensitive": bool(c.get("sensitive"))}
        for c in catalog if allowed or not c.get("sensitive")
    ]


def _resolve_columns(db: Session, user: User, entity: str, keys: list[str]) -> list[dict]:
    available = {c["key"]: c for c in columns_for(db, user, entity)}
    if not keys:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose at least one column to export")
    resolved, seen = [], set()
    for key in keys:
        if key in seen:
            continue                                   # a column repeated in the pattern counts once
        seen.add(key)
        column = available.get(key)
        if not column:
            # Either a typo/stale saved pattern, or a sensitive column the
            # caller may not see. Both are refused the same way, so the
            # error never reveals that the column exists.
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Column '{key}' is not available for export")
        resolved.append(column)
    return resolved


def _sensitive_values(db: Session, rows: list[dict]) -> dict[int, dict]:
    """Aadhaar/PAN come off the Employee, the rest off the newest
    StatutoryInfo/BankAccount row per episode. Fetched in two queries for
    the whole export, not per row."""
    from app.models.models import Employee, EmploymentEpisode

    episode_ids = [r["episode_id"] for r in rows]
    if not episode_ids:
        return {}
    by_episode: dict[int, dict] = {eid: {} for eid in episode_ids}

    identity = (
        db.query(EmploymentEpisode.id, Employee.aadhaar, Employee.pan)
        .join(Employee, Employee.id == EmploymentEpisode.employee_id)
        .filter(EmploymentEpisode.id.in_(episode_ids)).all()
    )
    for episode_id, aadhaar, pan in identity:
        by_episode[episode_id].update({"aadhaar": aadhaar, "pan": pan})

    # Oldest first, so the newest row for each episode wins the overwrite.
    for s in (db.query(StatutoryInfo).filter(StatutoryInfo.episode_id.in_(episode_ids))
              .order_by(StatutoryInfo.effective_from, StatutoryInfo.id).all()):
        by_episode[s.episode_id].update({
            "uan": s.uan, "esi_number": s.esi_number,
            "pf_eligible": s.pf_eligible, "esi_eligible": s.esi_eligible,
        })
    for b in (db.query(BankAccount).filter(BankAccount.episode_id.in_(episode_ids))
              .order_by(BankAccount.effective_from, BankAccount.id).all()):
        by_episode[b.episode_id].update({
            "bank_name": b.bank_name, "bank_branch": b.branch,
            "account_number": b.account_number, "ifsc": b.ifsc,
        })
    return by_episode


def _matches(row: dict, entity: str, filters: dict) -> bool:
    """The list pages' own filter semantics, server-side. Employees filter
    on resolved NAMES (that is what their list row carries and what the
    dropdowns are built from); candidates filter on ids."""
    def text(value: str | None) -> str:
        return (value or "").strip().lower()

    search = text(filters.get("search"))
    if search:
        digits = "".join(ch for ch in filters["search"] if ch.isdigit())
        haystack = [text(f"{row.get('first_name')} {row.get('last_name')}")]
        if entity == EMPLOYEE:
            haystack += [text(row.get("employee_number")), text(row.get("designation"))]
        else:
            haystack += [text(row.get("reference_number"))]
        if not any(search in h for h in haystack) and not (
            len(digits) >= 4 and digits in (row.get("mobile_number") or "")
        ):
            return False

    for key in FILTER_KEYS[entity]:
        if key == "search":
            continue
        wanted = filters.get(key)
        if wanted in (None, ""):
            continue
        if str(row.get(key)) != str(wanted):
            return False
    return True


def _sort_key(value: Any):
    """A key that never compares two different types against each other
    (which would raise on a column holding, say, both numbers and text)."""
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, (int, float)):
        return (0, value)
    if isinstance(value, (dt.datetime, dt.date)):
        return (1, value.isoformat())
    return (2, str(value).lower())


def _sort(rows: list[dict], key: str, descending: bool) -> list[dict]:
    """Blanks go last in BOTH directions - they are "no value", not the
    smallest one, so an export sorted by Separation Date should never open
    on a page of blanks whichever way it was sorted."""
    filled = [r for r in rows if r.get(key) not in (None, "")]
    blank = [r for r in rows if r.get(key) in (None, "")]
    filled.sort(key=lambda r: _sort_key(r.get(key)), reverse=descending)
    return filled + blank


def build_rows(db: Session, user: User, entity: str, spec: dict) -> tuple[list[dict], list[dict]]:
    """(columns, rows) for a spec - the single path both the preview and the
    download go through, so what is previewed is what is downloaded."""
    check_entity(entity)
    columns = _resolve_columns(db, user, entity, spec.get("columns") or [])
    filters = {k: v for k, v in (spec.get("filters") or {}).items() if k in FILTER_KEYS[entity]}

    if entity == EMPLOYEE:
        rows = employee_list_service.list_rows(db, user)
    else:
        rows = candidate_list_service.list_rows(db, user)
    rows = [r for r in rows if _matches(r, entity, filters)]

    if entity == EMPLOYEE and any(c["sensitive"] for c in columns):
        extra = _sensitive_values(db, rows)
        rows = [{**r, **extra.get(r["episode_id"], {})} for r in rows]

    sort_by = spec.get("sort_by")
    if sort_by:
        if sort_by not in {c["key"] for c in columns}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The sort column must be one of the exported columns")
        rows = _sort(rows, sort_by, descending=spec.get("sort_dir") == "desc")
    return columns, rows


def _cell(value: Any) -> Any:
    """Dates and numbers go in as themselves so Excel can sort and filter
    them; booleans become Yes/No, which is what the list page shows."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dt.datetime, dt.date, int, float)) or value is None:
        return value
    return str(value)


def build_workbook(db: Session, user: User, entity: str, spec: dict) -> tuple[Workbook, int]:
    columns, rows = build_rows(db, user, entity, spec)
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees" if entity == EMPLOYEE else "Candidates"

    ws.append([c["label"] for c in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        ws.append([_cell(row.get(c["key"])) for c in columns])

    for index, column in enumerate(columns, start=1):
        widest = max([len(column["label"])] + [len(str(r.get(column["key"]) or "")) for r in rows[:200]])
        ws.column_dimensions[get_column_letter(index)].width = min(max(widest + 2, 10), 42)
    for index, column in enumerate(columns, start=1):
        if any(isinstance(r.get(column["key"]), (dt.date, dt.datetime)) for r in rows[:200]):
            for cell in ws[get_column_letter(index)][1:]:
                cell.number_format = "dd-mm-yyyy"
    # A header filter and a frozen header row: an exported list is something
    # people keep working in, not just read.
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows) + 1}"
    ws.freeze_panes = "A2"
    return wb, len(rows)


# ---------------------------------------------------------------------------
# Saved patterns
# ---------------------------------------------------------------------------

def visible_templates(db: Session, user: User, entity: str | None = None) -> list[ExportTemplate]:
    """Your own patterns plus any shared one. Shared is how a pattern
    reaches a team - HR_ADMIN/SUPER_ADMIN can share, so one agreed
    "Payroll handover" layout can exist instead of six near-copies."""
    query = db.query(ExportTemplate).filter(
        (ExportTemplate.created_by_id == user.id) | (ExportTemplate.is_shared.is_(True))
    )
    if entity:
        query = query.filter(ExportTemplate.entity == check_entity(entity))
    return query.order_by(ExportTemplate.entity, ExportTemplate.name).all()


def _may_share(db: Session, user: User) -> bool:
    return permission_service.is_admin(db, user)


def template_dict(template: ExportTemplate, user: User) -> dict:
    return {
        "id": template.id, "name": template.name, "entity": template.entity,
        "columns": [c for c in (template.columns or "").split(",") if c],
        "sort_by": template.sort_by, "sort_dir": template.sort_dir,
        "is_shared": bool(template.is_shared),
        "owned": template.created_by_id == user.id,
        "created_at": template.created_at,
    }


def save_template(db: Session, user: User, payload: dict, template: ExportTemplate | None = None) -> ExportTemplate:
    entity = check_entity(payload["entity"])
    columns = _resolve_columns(db, user, entity, payload.get("columns") or [])
    sort_by = payload.get("sort_by") or None
    if sort_by and sort_by not in {c["key"] for c in columns}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The sort column must be one of the pattern's columns")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give the pattern a name")

    clash = db.query(ExportTemplate).filter(
        ExportTemplate.name == name, ExportTemplate.entity == entity, ExportTemplate.created_by_id == user.id,
    )
    if template:
        clash = clash.filter(ExportTemplate.id != template.id)
    if clash.first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"You already have a pattern named '{name}'")

    is_shared = bool(payload.get("is_shared"))
    if is_shared and not _may_share(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an HR Admin can share a pattern with everyone")

    if not template:
        template = ExportTemplate(created_by_id=user.id)
        db.add(template)
    template.name = name
    template.entity = entity
    template.columns = ",".join(c["key"] for c in columns)
    template.sort_by = sort_by
    template.sort_dir = "desc" if payload.get("sort_dir") == "desc" else "asc"
    template.is_shared = is_shared
    db.flush()
    return template


def get_own_template(db: Session, user: User, template_id: int) -> ExportTemplate:
    """A pattern you may change or delete: your own, or any one if you're an
    admin. A shared pattern someone else owns is readable, not editable."""
    template = db.query(ExportTemplate).filter(ExportTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export pattern not found")
    if template.created_by_id != user.id and not permission_service.is_admin(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This export pattern belongs to someone else")
    return template
