"""Module 3: Payroll processing - earned days, salary structure, statutory
deductions, payroll run processing/approval/locking, and Full & Final
Settlement (payroll side). See CLAUDE.md and the Module 3/4 plan for the
overall design; several calculations below are intentionally pragmatic
simplifications, each documented at the point it's made."""
import calendar
import datetime as dt
import math

from fastapi import HTTPException, status
from simpleeval import EvalWithCompoundTypes, InvalidExpression
from sqlalchemy.orm import Session

from app.models.enums import AuditAction, RoleName, TransactionType
from app.models.models import (
    AdhocPayEntry, Address, AttendanceRecord, CostAllocation, EmploymentEpisode,
    FullFinalSettlement, LeaveApplication, LeaveBalance, LeaveType, OrgAssignment,
    Payslip, PayslipCostSplit, PayslipLine, PayrollRun, ProfessionalTaxSlab,
    SalaryComponent, SalaryComponentOverride, SalaryStructureComponent, SalaryTemplate,
    SalaryTemplateComponent, SeparationRecord, StatutoryConfig, StatutoryInfo, User,
)
from app.services import approval_service, audit_service, employee_service


# ---------------------------------------------------------------------------
# Earned days
# ---------------------------------------------------------------------------

def compute_earned_days(db: Session, episode_id: int, year: int, month: int) -> dict:
    """Best-effort earned-days calculation for one calendar month, not an
    exhaustive reconciliation of every possible attendance/leave overlap.

    Simplifying assumptions (documented per the plan's instruction):
    - present_days counts AttendanceRecord rows with status PRESENT (1 day)
      or HALF_DAY (0.5 day) within the month.
    - paid_leave_days counts approved LeaveApplication days overlapping the
      month where LeaveType.is_paid is True (each application's `days` is
      prorated by the fraction of its date range that falls in this month -
      a reasonable approximation since `days` is stored for the whole
      application, not per-day).
    - lop_days (loss of pay) counts the equivalent overlap for is_paid=False
      leave, PLUS any AttendanceRecord day marked ABSENT that isn't already
      covered by an approved leave application for that date.
    - total_days is the calendar day count for the month (calendar.monthrange).
    """
    _, last_day = calendar.monthrange(year, month)
    month_start, month_end = dt.date(year, month, 1), dt.date(year, month, last_day)
    total_days = last_day

    attendance_rows = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.episode_id == episode_id, AttendanceRecord.date >= month_start, AttendanceRecord.date <= month_end)
        .all()
    )
    present_days = sum(1.0 for r in attendance_rows if r.status == "PRESENT")
    present_days += sum(0.5 for r in attendance_rows if r.status == "HALF_DAY")
    absent_dates = {r.date for r in attendance_rows if r.status == "ABSENT"}

    leave_rows = (
        db.query(LeaveApplication)
        .join(LeaveType, LeaveApplication.leave_type_id == LeaveType.id)
        .filter(
            LeaveApplication.episode_id == episode_id,
            LeaveApplication.status == "APPROVED",
            LeaveApplication.start_date <= month_end,
            LeaveApplication.end_date >= month_start,
        )
        .all()
    )

    paid_leave_days = 0.0
    lop_days = 0.0
    leave_covered_dates = set()
    for application in leave_rows:
        overlap_start = max(application.start_date, month_start)
        overlap_end = min(application.end_date, month_end)
        overlap_days_count = (overlap_end - overlap_start).days + 1
        span_days_count = (application.end_date - application.start_date).days + 1
        # Prorate the application's stored `days` (which may reflect a
        # half-day) by the fraction of the application that falls in this
        # month - a pragmatic approximation, not an exact per-day split.
        fraction = overlap_days_count / span_days_count if span_days_count else 0
        prorated_days = (application.days or 0) * fraction

        leave_type = db.query(LeaveType).filter(LeaveType.id == application.leave_type_id).first()
        if leave_type and leave_type.is_paid:
            paid_leave_days += prorated_days
        else:
            lop_days += prorated_days

        d = overlap_start
        while d <= overlap_end:
            leave_covered_dates.add(d)
            d += dt.timedelta(days=1)

    # ABSENT attendance days not already covered by an approved leave
    # application count as additional LOP days.
    lop_days += sum(1.0 for d in absent_dates if d not in leave_covered_dates)

    return {
        "present_days": round(present_days, 2),
        "paid_leave_days": round(paid_leave_days, 2),
        "lop_days": round(lop_days, 2),
        "total_days": total_days,
    }


def compute_day_variables(db: Session, episode_id: int, year: int, month: int) -> dict:
    """The day-count breakdown used as formula variables (PRESENT, ABSENT,
    HALF_DAY, ON_LEAVE, WEEKLY_OFF, HOLIDAY, LATE_DAYS, EARLY_DEP_DAYS,
    OT_MIN, NOT_MARKED) - mirrors AttendanceRegister.jsx's summarize()
    exactly (same status bucket names, same late/early/overtime/not-marked
    rules) so a formula's numbers match what HR already sees in the
    Attendance Register for the same period."""
    _, last_day = calendar.monthrange(year, month)
    month_start, month_end = dt.date(year, month, 1), dt.date(year, month, last_day)
    rows = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.episode_id == episode_id, AttendanceRecord.date >= month_start, AttendanceRecord.date <= month_end)
        .all()
    )
    counts = {k: 0 for k in ("PRESENT", "ABSENT", "HALF_DAY", "ON_LEAVE", "WEEKLY_OFF", "HOLIDAY")}
    late_days = early_days = not_marked = 0
    ot_minutes = 0.0
    for r in rows:
        if r.status and r.status in counts:
            counts[r.status] += 1
        elif not r.status:
            not_marked += 1
        if (r.late_minutes or 0) > 0:
            late_days += 1
        if (r.early_departure_minutes or 0) > 0:
            early_days += 1
        ot_minutes += r.overtime_minutes or 0
    return {
        **counts,
        "LATE_DAYS": late_days, "EARLY_DEP_DAYS": early_days, "OT_MIN": ot_minutes, "NOT_MARKED": not_marked,
    }


# ---------------------------------------------------------------------------
# Formula engine for FORMULA-type salary components
# ---------------------------------------------------------------------------

def _roundup(value: float, nearest: float = 1) -> float:
    """Rounds AWAY from zero to the nearest multiple of `nearest` - e.g.
    roundup(1234, 100) = 1300, roundup(0.751, 0.01) = 0.76. Same semantics
    as the ROUNDUP spreadsheet function (and salary-app's formula engine),
    for payroll rules like "round PF up to the nearest rupee"."""
    if nearest == 0:
        raise ValueError("roundup()'s second argument cannot be 0")
    factor = value / nearest
    rounded = math.ceil(factor) if factor >= 0 else math.floor(factor)
    return round(rounded * nearest, 10)


def _rounddown(value: float, nearest: float = 1) -> float:
    """Rounds TOWARD zero to the nearest multiple of `nearest` - the
    ROUNDDOWN counterpart to _roundup."""
    if nearest == 0:
        raise ValueError("rounddown()'s second argument cannot be 0")
    factor = value / nearest
    rounded = math.floor(factor) if factor >= 0 else math.ceil(factor)
    return round(rounded * nearest, 10)


def _formula_if(condition, true_value, false_value=0):
    """Excel-style IF(condition, true_value, false_value) - simpleeval
    already supports Python's `x if cond else y` ternary natively, but
    HR/finance users writing payroll formulas expect the spreadsheet
    function form, e.g. IF(PRESENT>=26, 500, 0)."""
    return true_value if condition else false_value


_BASE_FORMULA_FUNCTIONS = {
    "min": min, "max": max, "round": round, "abs": abs,
    "ceil": math.ceil, "floor": math.floor,
    "roundup": _roundup, "rounddown": _rounddown,
}
# Formulas are often typed in spreadsheet-style ALL CAPS (MIN/MAX/ROUNDUP/...)
# - accept both cases rather than forcing lowercase.
_SAFE_FORMULA_FUNCTIONS = {**_BASE_FORMULA_FUNCTIONS, **{name.upper(): fn for name, fn in _BASE_FORMULA_FUNCTIONS.items()}}
# IF/AND/OR: "if"/"and"/"or" are Python keywords, so a lowercase
# `if(...)` call is never valid syntax to begin with - only the
# spreadsheet-style ALL CAPS form (IF/AND/OR) can ever be used as a
# function name here, so these are registered uppercase-only.
_SAFE_FORMULA_FUNCTIONS["IF"] = _formula_if
_SAFE_FORMULA_FUNCTIONS["AND"] = lambda *args: all(args)
_SAFE_FORMULA_FUNCTIONS["OR"] = lambda *args: any(args)


def evaluate_formula(formula: str, context: dict) -> float:
    """Evaluates a formula string against a variable context (day
    variables + already-resolved component codes) using simpleeval - no
    access to Python builtins/attributes/imports, only the names in
    `context` and the whitelisted functions above."""
    try:
        evaluator = EvalWithCompoundTypes(names=context, functions=_SAFE_FORMULA_FUNCTIONS)
        result = evaluator.eval(formula)
    except (InvalidExpression, ZeroDivisionError, SyntaxError, TypeError, KeyError) as exc:
        raise ValueError(f"Formula error in '{formula}': {exc}")
    if not isinstance(result, (int, float)):
        raise ValueError(f"Formula '{formula}' did not evaluate to a number")
    return float(result)


def resolve_formula_components(
    rows: list, context: dict,
) -> tuple[dict[str, float], list[dict]]:
    """Multi-pass dependency resolution for a set of (component, formula)
    pairs that may reference each other's codes (e.g. GROSS references
    BASIC and HRA) - same idea as salary-app's formula engine. `rows` is
    a list of (code, formula) tuples. Returns (resolved: code -> value,
    errors: [{code, message}]) - a row whose formula still can't resolve
    after len(rows)+1 passes is a circular/missing reference and is
    reported as an error rather than looping forever."""
    pending = list(rows)
    resolved: dict[str, float] = {}
    errors = []
    max_passes = len(rows) + 1
    for _ in range(max_passes):
        if not pending:
            break
        still_pending = []
        made_progress = False
        for code, formula in pending:
            try:
                value = evaluate_formula(formula, {**context, **resolved})
                resolved[code] = value
                made_progress = True
            except ValueError:
                still_pending.append((code, formula))
        pending = still_pending
        if not made_progress:
            break
    for code, formula in pending:
        errors.append({"code": code, "message": f"Could not resolve formula '{formula}' (missing/circular reference)"})
    return resolved, errors


# A fully-worked, no-exceptions calendar month - the "sample payslip for
# 31 days" scenario used to preview a Salary Template or an employee's
# structure without needing real attendance data.
FULL_MONTH_DAY_VARS = {
    "PRESENT": 31, "ABSENT": 0, "HALF_DAY": 0, "ON_LEAVE": 0, "WEEKLY_OFF": 0, "HOLIDAY": 0,
    "LATE_DAYS": 0, "EARLY_DEP_DAYS": 0, "OT_MIN": 0, "NOT_MARKED": 0,
}


def preview_component_amounts(rows: list[dict], day_vars: dict = FULL_MONTH_DAY_VARS) -> dict:
    """Resolves a list of {code, name, component_type, amount, percentage,
    formula} component rows (from either a SalaryTemplate or an
    employee's active SalaryStructureComponent set) into concrete amounts
    for a preview - same FIXED/PERCENTAGE_OF_BASIC/FORMULA resolution as
    process_payroll_run, minus attendance proration (day_vars assumes a
    full month) and minus statutory PF/ESI/PT/LWF, which depend on a
    specific employee's eligibility flags and don't apply to a template
    or a hypothetical preview."""
    resolved_by_code: dict[str, float] = {}
    formula_rows = []
    meta_by_code = {}
    for row in rows:
        code = row["code"]
        meta_by_code[code] = row
        if row.get("formula"):
            formula_rows.append((code, row["formula"]))
        elif row.get("percentage") is not None:
            formula_rows.append((code, f"BASIC * {row['percentage']} / 100"))
        else:
            resolved_by_code[code] = round(row.get("amount") or 0.0, 2)

    errors = []
    if formula_rows:
        context = {**day_vars, **resolved_by_code}
        formula_resolved, formula_errors = resolve_formula_components(formula_rows, context)
        errors = formula_errors
        for code, value in formula_resolved.items():
            resolved_by_code[code] = round(value, 2)

    lines = []
    gross_earnings = 0.0
    gross_deductions = 0.0
    additional_pay = 0.0
    for code, amount in resolved_by_code.items():
        meta = meta_by_code.get(code, {})
        component_type = meta.get("component_type", "EARNING")
        if component_type == "EARNING":
            gross_earnings += amount
        elif component_type == "DEDUCTION":
            gross_deductions += amount
        elif component_type == "ADDITION":
            additional_pay += amount
        lines.append({"code": code, "name": meta.get("name", code), "component_type": component_type, "amount": amount})

    net_pay = round(gross_earnings - gross_deductions, 2)
    return {
        "lines": lines,
        "gross_earnings": round(gross_earnings, 2),
        "gross_deductions": round(gross_deductions, 2),
        "net_pay": net_pay,
        "additional_pay": round(additional_pay, 2),
        "total_payable": round(net_pay + additional_pay, 2),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Salary structure
# ---------------------------------------------------------------------------

def active_salary_structure(db: Session, episode_id: int, as_of_date: dt.date) -> list[SalaryStructureComponent]:
    return (
        db.query(SalaryStructureComponent)
        .filter(
            SalaryStructureComponent.episode_id == episode_id,
            SalaryStructureComponent.effective_from <= as_of_date,
            (SalaryStructureComponent.effective_to.is_(None)) | (SalaryStructureComponent.effective_to >= as_of_date),
        )
        .all()
    )


def salary_structure_history(db: Session, episode_id: int, component_id: int | None = None) -> list[SalaryStructureComponent]:
    """Every version (open and closed) of an episode's salary structure,
    newest effective_from first - the full "salary versioning by start
    and end date" record, vs. active_salary_structure's as-of-one-date
    snapshot."""
    query = db.query(SalaryStructureComponent).filter(SalaryStructureComponent.episode_id == episode_id)
    if component_id is not None:
        query = query.filter(SalaryStructureComponent.component_id == component_id)
    return query.order_by(SalaryStructureComponent.component_id, SalaryStructureComponent.effective_from.desc()).all()


# Alias matching the plan's Phase B naming (`resolve_salary_structure`).
resolve_salary_structure = active_salary_structure


def set_salary_structure_component(
    db: Session, episode_id: int, component_id: int, amount: float | None, percentage: float | None,
    effective_from: dt.date, user: User, formula: str | None = None,
) -> SalaryStructureComponent:
    """Closes any previously-open SalaryStructureComponent row(s) for this
    (episode_id, component_id) pair before inserting the new one - same
    close-prior-row pattern as employee_service.add_org_assignment.
    Queries ALL open rows (not just one) and closes every one that starts
    before the new version, so a same-day duplicate insert or any other
    edge case can never leave two rows simultaneously open - that
    invariant is what makes "versioning by start/end date" meaningful."""
    open_rows = (
        db.query(SalaryStructureComponent)
        .filter(
            SalaryStructureComponent.episode_id == episode_id,
            SalaryStructureComponent.component_id == component_id,
            SalaryStructureComponent.effective_to.is_(None),
        )
        .all()
    )
    for open_row in open_rows:
        if open_row.effective_from >= effective_from:
            raise ValueError(
                f"An existing version already starts on or after {effective_from} "
                f"(component {component_id}, starts {open_row.effective_from}) - "
                "choose a later start date, or end that version first."
            )
        open_row.effective_to = effective_from - dt.timedelta(days=1)
        db.add(open_row)

    row = SalaryStructureComponent(
        episode_id=episode_id, component_id=component_id, amount=amount, percentage=percentage,
        formula=formula, effective_from=effective_from,
    )
    db.add(row)
    db.flush()
    audit_service.record(db, "SALARY_STRUCTURE_COMPONENT", row.id, AuditAction.CREATE, user,
                          new_value=f"component={component_id} amount={amount} pct={percentage} formula={formula} from={effective_from}")
    return row


def end_salary_structure_component(db: Session, row_id: int, effective_to: dt.date, user: User) -> SalaryStructureComponent:
    """Discontinues a currently-open structure row as of `effective_to`
    with no replacement version - the other half of "versioning by
    starting and ending date" (set_salary_structure_component only ever
    starts a new version; this ends one outright, e.g. an employee opts
    out of Group Insurance with no successor row)."""
    row = db.query(SalaryStructureComponent).filter(SalaryStructureComponent.id == row_id).first()
    if not row:
        raise ValueError("Salary structure row not found")
    if row.effective_to is not None:
        raise ValueError("This row is already closed")
    if effective_to < row.effective_from:
        raise ValueError("End date cannot be before the start date")
    row.effective_to = effective_to
    db.add(row)
    audit_service.record(db, "SALARY_STRUCTURE_COMPONENT", row.id, AuditAction.UPDATE, user, new_value=f"ended {effective_to}")
    return row


# ---------------------------------------------------------------------------
# Salary templates (reusable structure blueprints, scoped to a Cost
# Center and/or Project, or global when both are null)
# ---------------------------------------------------------------------------

def matching_templates(db: Session, cost_center_id: int | None, project_id: int | None) -> list[SalaryTemplate]:
    """Templates whose own scope is either unset (matches anything on
    that dimension) or equal to the given cost_center_id/project_id -
    most-specific-first, same idea as ApprovalRule/LeaveEligibilityRule's
    matching cascade elsewhere in this app. A template scoped to a
    specific Project only matches that Project; one scoped only to a
    Cost Center matches any Project within it; a template with neither
    set is global and matches everything."""
    query = db.query(SalaryTemplate).filter(SalaryTemplate.is_active.is_(True))
    query = query.filter(
        (SalaryTemplate.cost_center_id.is_(None)) | (SalaryTemplate.cost_center_id == cost_center_id)
    )
    query = query.filter(
        (SalaryTemplate.project_id.is_(None)) | (SalaryTemplate.project_id == project_id)
    )
    templates = query.all()

    def specificity(t: SalaryTemplate) -> int:
        return (2 if t.project_id is not None else 0) + (1 if t.cost_center_id is not None else 0)

    return sorted(templates, key=specificity, reverse=True)


def apply_template(
    db: Session, episode_id: int, effective_from: dt.date,
    components: list[dict], user: User,
) -> tuple[list[SalaryStructureComponent], list[dict]]:
    """Applies a (possibly hand-edited) list of {component_id, amount,
    percentage, formula} rows to an episode's structure via
    set_salary_structure_component, one row at a time so one bad
    component (e.g. an overlapping version) doesn't block the rest."""
    applied = []
    errors = []
    for row in components:
        try:
            result = set_salary_structure_component(
                db, episode_id, row["component_id"], row.get("amount"), row.get("percentage"), effective_from, user,
                formula=row.get("formula"),
            )
            applied.append(result)
        except ValueError as exc:
            errors.append({"component_id": row["component_id"], "message": str(exc)})
    return applied, errors


# ---------------------------------------------------------------------------
# Salary component overrides (one-month exception to a recurring
# structure component, e.g. "Group Insurance is normally Rs.50 but wasn't
# collected this month - override it to 0 for this employee this month")
# ---------------------------------------------------------------------------

def get_override(db: Session, episode_id: int, component_id: int, year: int, month: int) -> SalaryComponentOverride | None:
    return (
        db.query(SalaryComponentOverride)
        .filter(
            SalaryComponentOverride.episode_id == episode_id,
            SalaryComponentOverride.component_id == component_id,
            SalaryComponentOverride.year == year,
            SalaryComponentOverride.month == month,
        )
        .first()
    )


def list_overrides(db: Session, episode_id: int, year: int, month: int) -> list[SalaryComponentOverride]:
    return (
        db.query(SalaryComponentOverride)
        .filter(
            SalaryComponentOverride.episode_id == episode_id,
            SalaryComponentOverride.year == year,
            SalaryComponentOverride.month == month,
        )
        .all()
    )


def set_override(db: Session, episode_id: int, component_id: int, year: int, month: int, amount: float, remarks: str | None, user: User) -> SalaryComponentOverride:
    """Upserts the (episode, component, year, month) override - re-setting
    an override for the same period replaces the previous value rather
    than stacking a second row (the unique constraint would reject a
    duplicate insert anyway)."""
    existing = get_override(db, episode_id, component_id, year, month)
    if existing:
        existing.amount = amount
        existing.remarks = remarks
        existing.created_by_id = user.id
        db.add(existing)
        audit_service.record(db, "SALARY_COMPONENT_OVERRIDE", existing.id, AuditAction.UPDATE, user,
                              new_value=f"component={component_id} {year}-{month} amount={amount}")
        return existing
    row = SalaryComponentOverride(
        episode_id=episode_id, component_id=component_id, year=year, month=month,
        amount=amount, remarks=remarks, created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    audit_service.record(db, "SALARY_COMPONENT_OVERRIDE", row.id, AuditAction.CREATE, user,
                          new_value=f"component={component_id} {year}-{month} amount={amount}")
    return row


def delete_override(db: Session, override_id: int, user: User):
    row = db.query(SalaryComponentOverride).filter(SalaryComponentOverride.id == override_id).first()
    if not row:
        raise ValueError("Override not found")
    audit_service.record(db, "SALARY_COMPONENT_OVERRIDE", row.id, "DELETE", user,
                          old_value=f"component={row.component_id} {row.year}-{row.month} amount={row.amount}")
    db.delete(row)


# ---------------------------------------------------------------------------
# Cost allocation
# ---------------------------------------------------------------------------

def active_cost_allocations(db: Session, episode_id: int, as_of_date: dt.date) -> list[CostAllocation]:
    return (
        db.query(CostAllocation)
        .filter(
            CostAllocation.episode_id == episode_id,
            CostAllocation.effective_from <= as_of_date,
            (CostAllocation.effective_to.is_(None)) | (CostAllocation.effective_to >= as_of_date),
        )
        .all()
    )


# ---------------------------------------------------------------------------
# Statutory config / PT / deductions
# ---------------------------------------------------------------------------

def active_statutory_config(db: Session, as_of_date: dt.date) -> StatutoryConfig:
    config = (
        db.query(StatutoryConfig)
        .filter(
            StatutoryConfig.effective_from <= as_of_date,
            (StatutoryConfig.effective_to.is_(None)) | (StatutoryConfig.effective_to >= as_of_date),
        )
        .order_by(StatutoryConfig.effective_from.desc())
        .first()
    )
    if not config:
        raise ValueError("No active StatutoryConfig found for this date - seed.py should have created one")
    return config


def resolve_professional_tax(db: Session, state: str | None, gross_earnings: float) -> float:
    """Returns 0 gracefully when no state is known, or no slab matches -
    ProfessionalTaxSlab is deliberately left unseeded (state-specific,
    admin-configured), so an empty/no-match table must not error."""
    if not state:
        return 0.0
    rows = (
        db.query(ProfessionalTaxSlab)
        .filter(ProfessionalTaxSlab.state == state, ProfessionalTaxSlab.is_active.is_(True))
        .all()
    )
    for row in rows:
        if gross_earnings >= (row.min_gross or 0) and (row.max_gross is None or gross_earnings <= row.max_gross):
            return row.monthly_amount
    return 0.0


def _employee_state(db: Session, episode: EmploymentEpisode) -> str | None:
    """Best-effort state lookup for PT slab resolution: prefers the
    employee's PRESENT address, falls back to PERMANENT."""
    addresses = db.query(Address).filter(Address.employee_id == episode.employee_id).all()
    by_type = {a.address_type: a for a in addresses}
    address = by_type.get("PRESENT") or by_type.get("PERMANENT")
    return address.state if address else None


# LWF frequency convention (not fully specified by the plan - documented
# here): MONTHLY applies every month; HALF_YEARLY applies in March and
# September (common Indian half-year-end convention); YEARLY applies in
# March only (Indian financial-year-end convention).
def _lwf_applies_this_month(frequency: str, month: int) -> bool:
    if frequency == "MONTHLY":
        return True
    if frequency == "HALF_YEARLY":
        return month in (3, 9)
    if frequency == "YEARLY":
        return month == 3
    return False


def compute_statutory_deductions(
    db: Session, episode_id: int, statutory_info: StatutoryInfo | None, gross_earnings: float,
    config: StatutoryConfig, employee_state: str | None, month: int,
) -> dict:
    """Returns {component_code: amount} for PF, EMPLOYER_PF, ESI,
    EMPLOYER_ESI, PT, LWF, EMPLOYER_LWF - gated by the episode's
    StatutoryInfo eligibility flags (a missing StatutoryInfo row is treated
    as not-eligible for everything, since none of the flags can be true)."""
    result = {}

    pf_eligible = bool(statutory_info and statutory_info.pf_eligible)
    esi_eligible = bool(statutory_info and statutory_info.esi_eligible)
    pt_eligible = bool(statutory_info and statutory_info.pt_eligible)

    if pf_eligible:
        pf_wage = min(gross_earnings, config.pf_wage_ceiling)
        result["PF"] = round(config.pf_employee_rate * pf_wage, 2)
        result["EMPLOYER_PF"] = round(config.pf_employer_rate * pf_wage, 2)
    else:
        result["PF"] = 0.0
        result["EMPLOYER_PF"] = 0.0

    if esi_eligible and gross_earnings <= config.esi_wage_ceiling:
        result["ESI"] = round(config.esi_employee_rate * gross_earnings, 2)
        result["EMPLOYER_ESI"] = round(config.esi_employer_rate * gross_earnings, 2)
    else:
        result["ESI"] = 0.0
        result["EMPLOYER_ESI"] = 0.0

    result["PT"] = round(resolve_professional_tax(db, employee_state, gross_earnings), 2) if pt_eligible else 0.0

    if _lwf_applies_this_month(config.lwf_frequency, month):
        result["LWF"] = round(config.lwf_employee_amount or 0, 2)
        result["EMPLOYER_LWF"] = round(config.lwf_employer_amount or 0, 2)
    else:
        result["LWF"] = 0.0
        result["EMPLOYER_LWF"] = 0.0

    return result


# ---------------------------------------------------------------------------
# Payroll run processing
# ---------------------------------------------------------------------------

def _get_or_create_run(db: Session, cost_center_id: int | None, year: int, month: int) -> PayrollRun:
    run = (
        db.query(PayrollRun)
        .filter(PayrollRun.cost_center_id == cost_center_id, PayrollRun.year == year, PayrollRun.month == month)
        .first()
    )
    if not run:
        run = PayrollRun(cost_center_id=cost_center_id, year=year, month=month, status="DRAFT")
        db.add(run)
        db.flush()
    return run


def _delete_existing_payslip(db: Session, run_id: int, episode_id: int):
    existing = db.query(Payslip).filter(Payslip.run_id == run_id, Payslip.episode_id == episode_id).first()
    if existing:
        db.query(PayslipLine).filter(PayslipLine.payslip_id == existing.id).delete()
        db.query(PayslipCostSplit).filter(PayslipCostSplit.payslip_id == existing.id).delete()
        db.delete(existing)
        db.flush()


def process_payroll_run(db: Session, cost_center_id: int | None, year: int, month: int, user: User) -> tuple[PayrollRun, list[dict]]:
    """Processes (or re-processes) a payroll run. Refuses reprocessing once
    APPROVED/LOCKED (the explicit gap this repo closes vs. salary-app).
    Returns (run, errors) - errors is a list of {episode_id, message} for
    episodes that failed, collected so one bad episode doesn't abort the
    whole run."""
    run = _get_or_create_run(db, cost_center_id, year, month)
    if run.status in ("APPROVED", "LOCKED"):
        raise ValueError(f"Payroll run is already {run.status} - cannot reprocess")

    _, last_day = calendar.monthrange(year, month)
    month_start, month_end = dt.date(year, month, 1), dt.date(year, month, last_day)
    as_of = month_end

    config = active_statutory_config(db, as_of)
    episodes = employee_service.episodes_in_cost_center_during(db, cost_center_id, month_start, month_end)

    errors = []
    for episode in episodes:
        savepoint = db.begin_nested()
        try:
            _delete_existing_payslip(db, run.id, episode.id)

            earned = compute_earned_days(db, episode.id, year, month)
            total_days = earned["total_days"] or 1
            proration_factor = min(1.0, (earned["present_days"] + earned["paid_leave_days"]) / total_days)

            structure_rows = active_salary_structure(db, episode.id, as_of)
            statutory_info = (
                db.query(StatutoryInfo)
                .filter(StatutoryInfo.episode_id == episode.id, StatutoryInfo.effective_to.is_(None))
                .order_by(StatutoryInfo.effective_from.desc())
                .first()
            )
            employee_state = _employee_state(db, episode)

            day_vars = compute_day_variables(db, episode.id, year, month)

            lines = []  # (code, name, type, amount)
            gross_earnings = 0.0
            gross_deductions = 0.0
            additional_pay = 0.0
            resolved_by_code: dict[str, float] = {}
            meta_by_code: dict[str, SalaryComponent] = {}
            formula_rows = []  # (code, formula) still to resolve

            for row in structure_rows:
                component = db.query(SalaryComponent).filter(SalaryComponent.id == row.component_id).first()
                if not component or component.is_statutory or component.component_type not in ("EARNING", "DEDUCTION", "ADDITION"):
                    continue
                meta_by_code[component.code] = component

                override = get_override(db, episode.id, component.id, year, month)
                if override is not None:
                    # An explicit override (e.g. this month's actual
                    # Performance Bonus figure, or "Group Insurance is
                    # normally Rs.50 but wasn't collected this month, use
                    # 0 instead") is used exactly as entered - no
                    # proration/formula, since the whole point is a
                    # one-off exact value for this employee this period.
                    # This is also the normal way to feed a monthly-
                    # variable ADDITION component (e.g. attendance-linked
                    # bonus) its actual figure each period.
                    resolved_by_code[component.code] = round(override.amount, 2)
                    continue

                formula = row.formula or component.formula
                if component.default_calculation == "FORMULA" and formula:
                    formula_rows.append((component.code, formula))
                elif component.default_calculation == "PERCENTAGE_OF_BASIC" and row.percentage is not None:
                    # Sugar for a formula referencing BASIC - resolved in
                    # the same multi-pass pass as any other formula, so it
                    # naturally waits for BASIC if BASIC is itself a
                    # not-yet-resolved formula.
                    formula_rows.append((component.code, f"BASIC * {row.percentage} / 100"))
                else:
                    base_amount = row.amount if row.amount is not None else 0.0
                    # Earnings and additions (bonus/performance/attendance
                    # pay) are prorated by attendance; recurring
                    # deductions (e.g. an insurance premium) are a fixed
                    # monthly amount.
                    amount = round(base_amount * proration_factor, 2) if component.component_type in ("EARNING", "ADDITION") else round(base_amount, 2)
                    resolved_by_code[component.code] = amount

            if formula_rows:
                formula_context = {**day_vars, **resolved_by_code}
                formula_resolved, formula_errors = resolve_formula_components(formula_rows, formula_context)
                if formula_errors:
                    raise ValueError("; ".join(f"{e['code']}: {e['message']}" for e in formula_errors))
                for code, value in formula_resolved.items():
                    resolved_by_code[code] = round(value, 2)

            for code, amount in resolved_by_code.items():
                component = meta_by_code.get(code)
                if not component:
                    continue
                if component.component_type == "EARNING":
                    gross_earnings += amount
                elif component.component_type == "DEDUCTION":
                    gross_deductions += amount
                else:  # ADDITION - paid out, but deliberately excluded from
                    # gross_earnings/net_pay and the PF/ESI wage base below.
                    additional_pay += amount
                lines.append((code, component.name, component.component_type, amount))

            statutory_amounts = compute_statutory_deductions(db, episode.id, statutory_info, gross_earnings, config, employee_state, month)
            component_meta = {c.code: c for c in db.query(SalaryComponent).filter(SalaryComponent.is_statutory.is_(True)).all()}

            # gross_deductions already carries any non-statutory structure
            # deductions (e.g. Group Insurance) accumulated above.
            employer_contributions = 0.0
            for code in ("PF", "ESI", "PT", "LWF"):
                amount = statutory_amounts.get(code, 0.0)
                if amount:
                    meta = component_meta.get(code)
                    lines.append((code, meta.name if meta else code, "DEDUCTION", amount))
                    gross_deductions += amount
            for code, employer_code in (("PF", "EMPLOYER_PF"), ("ESI", "EMPLOYER_ESI"), ("LWF", "EMPLOYER_LWF")):
                amount = statutory_amounts.get(employer_code, 0.0)
                if amount:
                    meta = component_meta.get(employer_code)
                    lines.append((employer_code, meta.name if meta else employer_code, "EMPLOYER_CONTRIBUTION", amount))
                    employer_contributions += amount

            adhoc_rows = (
                db.query(AdhocPayEntry)
                .filter(AdhocPayEntry.episode_id == episode.id, AdhocPayEntry.year == year, AdhocPayEntry.month == month)
                .all()
            )
            for adhoc in adhoc_rows:
                if adhoc.is_earning:
                    gross_earnings += adhoc.amount
                    lines.append((f"ADHOC_{adhoc.id}", adhoc.label, "EARNING", adhoc.amount))
                else:
                    gross_deductions += adhoc.amount
                    lines.append((f"ADHOC_{adhoc.id}", adhoc.label, "DEDUCTION", adhoc.amount))

            net_pay = round(gross_earnings - gross_deductions, 2)
            employer_cost_total = round(gross_earnings + employer_contributions, 2)
            additional_pay = round(additional_pay, 2)
            total_payable = round(net_pay + additional_pay, 2)

            payslip = Payslip(
                run_id=run.id, episode_id=episode.id,
                present_days=earned["present_days"], paid_leave_days=earned["paid_leave_days"], lop_days=earned["lop_days"],
                gross_earnings=round(gross_earnings, 2), gross_deductions=round(gross_deductions, 2),
                net_pay=net_pay, employer_cost_total=employer_cost_total,
                additional_pay=additional_pay, total_payable=total_payable, generated_at=dt.datetime.utcnow(),
            )
            db.add(payslip)
            db.flush()

            for code, name, comp_type, amount in lines:
                db.add(PayslipLine(payslip_id=payslip.id, component_code=code, component_name=name, component_type=comp_type, amount=amount))

            allocations = active_cost_allocations(db, episode.id, as_of)
            if allocations:
                for alloc in allocations:
                    split_amount = round(gross_earnings * (alloc.percentage / 100.0), 2)
                    db.add(PayslipCostSplit(
                        payslip_id=payslip.id, cost_center_id=alloc.cost_center_id, project_id=alloc.project_id,
                        percentage=alloc.percentage, amount=split_amount,
                    ))
            else:
                fallback_cc = approval_service.current_cost_center_id(db, episode.id)
                if fallback_cc:
                    db.add(PayslipCostSplit(
                        payslip_id=payslip.id, cost_center_id=fallback_cc, project_id=None,
                        percentage=100.0, amount=round(gross_earnings, 2),
                    ))
            savepoint.commit()
        except Exception as exc:  # noqa: BLE001 - deliberately broad: isolate one bad episode from the rest of the run
            savepoint.rollback()
            errors.append({"episode_id": episode.id, "employee_number": episode.employee_number, "message": str(exc)})

    run.status = "PROCESSED"
    run.processed_by_id = user.id
    run.processed_at = dt.datetime.utcnow()
    db.add(run)
    audit_service.record(db, "PAYROLL_RUN", run.id, AuditAction.UPDATE, user, new_value=f"PROCESSED errors={len(errors)}")
    return run, errors


# ---------------------------------------------------------------------------
# Approve / Lock
# ---------------------------------------------------------------------------

def approve_payroll_run(db: Session, run_id: int, user: User) -> PayrollRun:
    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if not run:
        raise ValueError("Payroll run not found")
    if run.status != "PROCESSED":
        raise ValueError("Only a PROCESSED payroll run can be approved")

    if user.role.name not in (RoleName.HR_ADMIN, RoleName.SUPER_ADMIN):
        rule = approval_service.find_approval_rule(db, TransactionType.PAYROLL_PROCESSING, run.cost_center_id, None)
        if rule:
            if rule.approver_user_id is not None:
                if user.id != rule.approver_user_id:
                    raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the assigned approver for this payroll run")
            elif user.role.name != rule.approver_role:
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role {rule.approver_role} to approve this payroll run")
        else:
            if user.role.name != RoleName.APPROVER:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires the Approver role (no approval rule matched)")

    run.status = "APPROVED"
    run.approved_by_id = user.id
    run.approved_at = dt.datetime.utcnow()
    db.add(run)
    audit_service.record(db, "PAYROLL_RUN", run.id, AuditAction.APPROVE, user)
    return run


def lock_payroll_run(db: Session, run_id: int, user: User) -> PayrollRun:
    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if not run:
        raise ValueError("Payroll run not found")
    if run.status != "APPROVED":
        raise ValueError("Only an APPROVED payroll run can be locked")

    run.status = "LOCKED"
    run.locked_at = dt.datetime.utcnow()
    db.add(run)
    audit_service.record(db, "PAYROLL_RUN", run.id, AuditAction.STATUS_CHANGE, user, new_value="LOCKED")
    return run


# ---------------------------------------------------------------------------
# Full & Final Settlement (payroll side)
# ---------------------------------------------------------------------------

def process_full_final_settlement(db: Session, episode_id: int, user: User) -> FullFinalSettlement:
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == episode_id).first()
    if not episode:
        raise ValueError("Employee record not found")

    separation = db.query(SeparationRecord).filter(SeparationRecord.episode_id == episode_id).first()
    if not separation:
        raise ValueError("No SeparationRecord exists for this employee - cannot process Full & Final Settlement")

    as_of = separation.last_working_date or separation.resignation_date or dt.date.today()
    config = active_statutory_config(db, as_of)

    # Last drawn BASIC component, used both for leave-encashment daily rate
    # and gratuity - simplification: last active SalaryStructureComponent
    # row for the BASIC code as of the separation date.
    basic_component = db.query(SalaryComponent).filter(SalaryComponent.code == "BASIC").first()
    last_drawn_basic = 0.0
    if basic_component:
        structure_row = (
            db.query(SalaryStructureComponent)
            .filter(SalaryStructureComponent.episode_id == episode_id, SalaryStructureComponent.component_id == basic_component.id)
            .filter(SalaryStructureComponent.effective_from <= as_of)
            .order_by(SalaryStructureComponent.effective_from.desc())
            .first()
        )
        if structure_row:
            last_drawn_basic = structure_row.amount or 0.0

    # Leave encashment: sum unused balance (opening+accrued+adjusted-used)
    # across paid leave types only, at a daily rate of last_drawn_basic/30 -
    # a reasonable simplification (documented per the plan) since this repo
    # has no separate "encashable" flag on LeaveType.
    balances = db.query(LeaveBalance).filter(LeaveBalance.episode_id == episode_id).all()
    leave_encashment_days = 0.0
    for balance in balances:
        leave_type = db.query(LeaveType).filter(LeaveType.id == balance.leave_type_id).first()
        if not leave_type or not leave_type.is_paid:
            continue
        available = (balance.opening_balance or 0) + (balance.accrued or 0) + (balance.adjusted or 0) - (balance.used or 0)
        if available > 0:
            leave_encashment_days += available
    daily_rate = (last_drawn_basic / 30.0) if last_drawn_basic else 0.0
    leave_encashment_amount = round(leave_encashment_days * daily_rate, 2)

    # Gratuity: statutory eligibility requires >= 5 years of service (Payment
    # of Gratuity Act 1972), AND the episode's StatutoryInfo.gratuity_eligible
    # flag. gratuity_years_of_service uses date_of_joining -> as_of, as a
    # float (days/365.25) - approximate, not a court-precise day count.
    gratuity_years_of_service = 0.0
    if episode.date_of_joining:
        gratuity_years_of_service = round((as_of - episode.date_of_joining).days / 365.25, 2)

    statutory_info = (
        db.query(StatutoryInfo)
        .filter(StatutoryInfo.episode_id == episode_id, StatutoryInfo.effective_to.is_(None))
        .order_by(StatutoryInfo.effective_from.desc())
        .first()
    )
    gratuity_amount = 0.0
    if gratuity_years_of_service >= 5 and statutory_info and statutory_info.gratuity_eligible:
        gratuity_amount = round(last_drawn_basic / config.gratuity_divisor * config.gratuity_days_per_year * gratuity_years_of_service, 2)

    # Notice pay recovery: no notice-period-shortfall data is modeled yet
    # (would need actual last-working-date vs. required notice comparison
    # against a tracked "notice served" figure) - left at 0 for v1, per the
    # plan's explicit allowance for this simplification.
    notice_pay_recovery = 0.0

    # Other dues: AdhocPayEntry always requires year/month per Phase A's
    # schema, so there's no natural "undated dues" bucket to sum here for
    # v1 - left at 0, per the plan's explicit allowance for this simplification.
    other_dues = 0.0

    net_payable = round(leave_encashment_amount + gratuity_amount - notice_pay_recovery + other_dues, 2)

    settlement = db.query(FullFinalSettlement).filter(FullFinalSettlement.episode_id == episode_id).first()
    if not settlement:
        settlement = FullFinalSettlement(episode_id=episode_id)

    settlement.separation_id = separation.id
    settlement.leave_encashment_days = round(leave_encashment_days, 2)
    settlement.leave_encashment_amount = leave_encashment_amount
    settlement.gratuity_years_of_service = gratuity_years_of_service
    settlement.gratuity_amount = gratuity_amount
    settlement.notice_pay_recovery = notice_pay_recovery
    settlement.other_dues = other_dues
    settlement.net_payable = net_payable
    settlement.status = "COMPLETED"
    settlement.processed_at = dt.datetime.utcnow()
    db.add(settlement)
    db.flush()

    separation.full_final_status = "COMPLETED"
    db.add(separation)

    audit_service.record(db, "FULL_FINAL_SETTLEMENT", settlement.id, AuditAction.UPDATE, user, new_value=f"net_payable={net_payable}")
    return settlement
