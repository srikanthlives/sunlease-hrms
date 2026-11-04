"""Employee feed for the depot management app (sunlease-depot-mgt).

The depot app rosters crew onto buses, so it wants only the operating crew and
in its own vocabulary: `full_name` rather than first/last, `start_date` rather
than `date_of_joining`, a depot *code* rather than a work-location name, and a
`staff_type` of DRIVER / CONDUCTOR / DEPOT_STAFF, which HRMS does not record.

The translation lives here, on the HRMS side, because HRMS owns these masters
and renames them; the depot app is left with no knowledge of this schema.
"""
import datetime as dt
import json
import os

from sqlalchemy.orm import Session, joinedload

from app.models.models import Designation, EmployeeCategory, EmploymentEpisode

# Which employees the depot gets, and what staff_type each becomes. Matched on
# the master *names*, case-insensitively, because both masters are
# admin-configurable. Override with HRMS_DEPOT_EXPORT_RULES (same JSON shape)
# when a name changes, rather than editing code.
DEFAULT_RULES = [
    {"employee_category": "Operations Staff", "designation": "Coach Captain", "staff_type": "DRIVER"},
]

# An episode is sent only in these states. DRAFT / PENDING_APPROVAL / APPROVED
# are half-entered records, so they must never reach a roster; SEPARATED and
# the rest are sent as INACTIVE so the depot can close the stint rather than
# silently keep a leaver rosterable.
STATUS_MAP = {
    "ACTIVE": "ACTIVE",
    "NOTICE_PERIOD": "ACTIVE",
    "INACTIVE": "INACTIVE",
    "SUSPENDED": "INACTIVE",
    "SEPARATED": "INACTIVE",
}


def rules() -> list[dict]:
    raw = os.environ.get("HRMS_DEPOT_EXPORT_RULES")
    if not raw:
        return DEFAULT_RULES
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"HRMS_DEPOT_EXPORT_RULES is not valid JSON: {exc}")
    if not isinstance(parsed, list) or not all(isinstance(r, dict) for r in parsed):
        raise ValueError("HRMS_DEPOT_EXPORT_RULES must be a list of objects")
    return parsed


def _key(*names) -> tuple:
    return tuple((n or "").strip().lower() for n in names)


def staff_type_for(category_name: str | None, designation_name: str | None,
                   rule_list: list[dict] | None = None) -> str | None:
    """The depot staff_type for one (category, designation) pair, or None when
    the pair is not one the depot asked for."""
    for r in rule_list if rule_list is not None else rules():
        if _key(r.get("employee_category"), r.get("designation")) == _key(category_name, designation_name):
            return r["staff_type"]
    return None


def _iso(d: dt.date | None) -> str | None:
    return d.isoformat() if d else None


def employees(db: Session) -> list[dict]:
    """The depot app's eight fields, one row per employment episode it wants."""
    rule_list = rules()
    rows = []
    query = (db.query(EmploymentEpisode)
             .options(joinedload(EmploymentEpisode.employee),
                      joinedload(EmploymentEpisode.designation),
                      joinedload(EmploymentEpisode.employee_category),
                      joinedload(EmploymentEpisode.work_location))
             .filter(EmploymentEpisode.status.in_(STATUS_MAP)))
    for e in query.order_by(EmploymentEpisode.employee_number, EmploymentEpisode.date_of_joining):
        staff_type = staff_type_for(e.employee_category.name if e.employee_category else None,
                                    e.designation.name if e.designation else None, rule_list)
        if staff_type is None:
            continue
        if not e.date_of_joining:
            continue  # the depot keys a stint on its start date, so a blank one is unusable
        full_name = " ".join(p for p in (e.employee.first_name, e.employee.last_name) if p).strip()
        rows.append({
            "employee_number": e.employee_number,
            "full_name": full_name,
            "designation": e.designation.name if e.designation else None,
            "staff_type": staff_type,
            "home_depot_code": e.work_location.code if e.work_location else None,
            "start_date": _iso(e.date_of_joining),
            "end_date": _iso(e.separation_date),
            "status": STATUS_MAP[e.status],
        })
    return rows


def selectable(db: Session) -> dict:
    """What the rules currently match, for an admin checking the setup."""
    cats = {c.name for c in db.query(EmployeeCategory)}
    desigs = {d.name for d in db.query(Designation)}
    out = []
    for r in rules():
        out.append({**r,
                    "employee_category_exists": r.get("employee_category") in cats,
                    "designation_exists": r.get("designation") in desigs})
    return {"rules": out, "employee_categories": sorted(cats), "designations": sorted(desigs)}
