"""
Core payroll computation engine.

Resolution order per employee/month:
 1. Load employee's active salary template components (in template-defined order -
    this same order is preserved on the payslip).
 2. Build a context of attendance variables (TOTAL_DAYS, PRESENT_DAYS, LOP_DAYS,
    PAID_LEAVE_DAYS, ATTENDANCE_RATIO).
 3. Resolve each component's value:
      - is_variable=True  -> monthly override (if uploaded) else default_value
      - calculation_type=FIXED       -> component.value
      - calculation_type=PERCENTAGE  -> component.value% of a base amount, where the base
                                         is itself a full formula expression (e.g. "BASIC + DA"),
                                         not just a single component code
      - calculation_type=FORMULA     -> safe-eval `formula` expression against
                                         already-resolved component codes + attendance vars,
                                         with min/max/round/abs/roundup/rounddown/ceil/floor available
    Components may depend on each other, so resolution is done in multiple passes
    (like a tiny dependency graph) until everything resolves or nothing more can progress.
 4. Optionally prorate a resolved value by attendance ratio (prorate_by_attendance flag).
 5. Add ad-hoc one-off entries (e.g. uniform deduction) on top.
 6. Sum earnings / deductions -> gross earnings, gross deductions, net pay.
    EMPLOYER_CONTRIBUTION components (e.g. Employer PF) are resolved but excluded from the
    payslip's earnings/deductions/net pay - they only roll up into employer_cost_total / ctc_total.
    REFERENCE components (e.g. GROSS_SALARY used to compute ESIC) are resolved into the
    formula context so other components can use them, but are never summed or shown anywhere
    as money - they're a pure calculation helper.
"""
from dataclasses import dataclass, field
import math
from simpleeval import EvalWithCompoundTypes, NameNotDefined
from sqlalchemy.orm import Session

from . import models
from .utils.attendance_calc import compute_monthly_attendance_stats


def _roundup(value, nearest=1):
    """Round UP to the nearest multiple of `nearest` (default 1 = nearest whole number)."""
    nearest = nearest or 1
    return math.ceil(value / nearest) * nearest


def _rounddown(value, nearest=1):
    """Round DOWN to the nearest multiple of `nearest` (default 1 = nearest whole number)."""
    nearest = nearest or 1
    return math.floor(value / nearest) * nearest


# Functions exposed to FORMULA (and formula-based PERCENTAGE) components, on top of
# simpleeval's built-in operators (+ - * / % ** comparisons, and/or/not, and the
# ternary `a if cond else b`). This is what lets you write capped/conditional/rounded
# formulas, e.g. a PF ceiling: min(BASIC + DA, 15000) * 0.12
# or rounding an allowance up to the nearest 10: roundup(BASIC * 0.05, 10)
SAFE_FORMULA_FUNCTIONS = {
    "min": min,
    "max": max,
    "round": round,
    "abs": abs,
    "roundup": _roundup,
    "rounddown": _rounddown,
    "ceil": math.ceil,
    "floor": math.floor,
}


@dataclass
class ComputedLine:
    code: str
    name: str
    component_type: str  # earning / deduction
    amount: float
    source: str  # template_default | variable_override | adhoc


@dataclass
class PayslipComputation:
    lines: list[ComputedLine] = field(default_factory=list)
    gross_earnings: float = 0.0
    gross_deductions: float = 0.0
    net_pay: float = 0.0
    employer_cost_total: float = 0.0
    ctc_total: float = 0.0
    template_no: str | None = None
    present_days: float = 0.0
    total_days: float = 0.0
    warnings: list[str] = field(default_factory=list)


class PayrollError(Exception):
    pass


def resolve_template_for_period(db: Session, employee: models.Employee, month: int, year: int) -> models.SalaryTemplate | None:
    """
    Picks whichever salary template is effective for the given employee in the given
    month/year, honoring dated overrides (EmployeeTemplateAssignment): the most recent
    assignment whose (effective_year, effective_month) is <= (year, month) wins. If no
    assignment applies yet (either none exist, or all of them start later than this
    period), Employee.template_id is used as the default/fallback.
    """
    assignment = (
        db.query(models.EmployeeTemplateAssignment)
        .filter(models.EmployeeTemplateAssignment.employee_id == employee.id)
        .filter(
            (models.EmployeeTemplateAssignment.effective_year < year)
            | (
                (models.EmployeeTemplateAssignment.effective_year == year)
                & (models.EmployeeTemplateAssignment.effective_month <= month)
            )
        )
        .order_by(
            models.EmployeeTemplateAssignment.effective_year.desc(),
            models.EmployeeTemplateAssignment.effective_month.desc(),
            models.EmployeeTemplateAssignment.id.desc(),
        )
        .first()
    )
    if assignment:
        return assignment.template
    return employee.template


def compute_payslip(db: Session, employee: models.Employee, month: int, year: int) -> PayslipComputation:
    template = resolve_template_for_period(db, employee, month, year)
    if template is None:
        raise PayrollError(
            f"Employee {employee.employee_code} has no salary template effective for {month}/{year} "
            f"(no default template set and no template assignment applies yet for this period)."
        )

    components = [c for c in template.components if c.is_active]
    if not components:
        raise PayrollError(f"Template '{template.template_no}' has no active components.")

    result = PayslipComputation()
    result.template_no = template.template_no

    # --- 1. Attendance context ---
    # Prefer the day-by-day attendance system; fall back to the legacy monthly summary row,
    # and finally to "assume full attendance" if neither exists for this employee/month.
    daily_stats = compute_monthly_attendance_stats(db, employee.id, month, year)
    if daily_stats:
        total_days = daily_stats["total_days"]
        present_days = daily_stats["present_days"]
        lop_days = daily_stats["lop_days"]
        paid_leave_days = daily_stats["paid_leave_days"]
    else:
        attendance = (
            db.query(models.Attendance)
            .filter_by(employee_id=employee.id, month=month, year=year)
            .first()
        )
        if attendance:
            total_days = attendance.total_days
            present_days = attendance.present_days
            lop_days = attendance.lop_days
            paid_leave_days = attendance.paid_leave_days
        else:
            # No attendance recorded at all: assume full attendance, but warn.
            total_days = 30.0
            present_days = 30.0
            lop_days = 0.0
            paid_leave_days = 0.0
            result.warnings.append(
                f"No attendance record found for {employee.employee_code} ({month}/{year}); assumed full attendance."
            )

    attendance_ratio = (present_days / total_days) if total_days else 0.0
    result.present_days = present_days
    result.total_days = total_days

    context: dict[str, float] = {
        "TOTAL_DAYS": total_days,
        "PRESENT_DAYS": present_days,
        "LOP_DAYS": lop_days,
        "PAID_LEAVE_DAYS": paid_leave_days,
        "ATTENDANCE_RATIO": attendance_ratio,
    }

    # --- 2. Monthly variable overrides for this employee/month ---
    overrides = {
        v.component_code: v.value
        for v in db.query(models.MonthlyVariableInput).filter_by(
            employee_id=employee.id, month=month, year=year
        ).all()
    }

    resolved_source: dict[str, str] = {}
    pending = list(components)
    max_passes = len(components) + 3

    for _ in range(max_passes):
        if not pending:
            break
        still_pending = []
        for comp in pending:
            value = None
            source = "template_default"

            if comp.is_variable:
                if comp.code in overrides:
                    value = overrides[comp.code]
                    source = "variable_override"
                else:
                    value = comp.default_value
                    source = "template_default"
            elif comp.calculation_type == models.CalculationType.FIXED:
                value = comp.value
            elif comp.calculation_type == models.CalculationType.PERCENTAGE:
                base_expr = (comp.formula or "").strip()
                try:
                    evaluator = EvalWithCompoundTypes(names=context, functions=SAFE_FORMULA_FUNCTIONS)
                    base_value = float(evaluator.eval(base_expr or "0"))
                except NameNotDefined:
                    still_pending.append(comp)
                    continue
                except Exception as e:
                    result.warnings.append(f"Percentage base error in component '{comp.code}': {e}")
                    base_value = 0.0
                value = base_value * (comp.value / 100.0)
            elif comp.calculation_type == models.CalculationType.FORMULA:
                try:
                    evaluator = EvalWithCompoundTypes(names=context, functions=SAFE_FORMULA_FUNCTIONS)
                    value = float(evaluator.eval(comp.formula or "0"))
                except NameNotDefined:
                    still_pending.append(comp)
                    continue
                except Exception as e:
                    result.warnings.append(f"Formula error in component '{comp.code}': {e}")
                    value = 0.0
            else:
                value = 0.0

            if comp.prorate_by_attendance and total_days:
                value = value * attendance_ratio

            context[comp.code] = round(value, 2)
            resolved_source[comp.code] = source
        pending = still_pending

    if pending:
        for comp in pending:
            result.warnings.append(
                f"Could not resolve component '{comp.code}' (circular/missing dependency); defaulted to 0."
            )
            context[comp.code] = 0.0
            resolved_source[comp.code] = "unresolved"

    # --- 3. Build lines from template components ---
    for comp in components:
        amount = context.get(comp.code, 0.0)
        result.lines.append(
            ComputedLine(
                code=comp.code,
                name=comp.name,
                component_type=comp.component_type.value,
                amount=amount,
                source=resolved_source.get(comp.code, "template_default"),
            )
        )
        if comp.component_type == models.ComponentType.EARNING:
            result.gross_earnings += amount
        elif comp.component_type == models.ComponentType.DEDUCTION:
            result.gross_deductions += amount
        elif comp.component_type == models.ComponentType.EMPLOYER_CONTRIBUTION:
            # Cost-to-company only: never touches gross earnings/deductions or net pay,
            # and is excluded from the payslip view - only surfaced in the CTC breakdown.
            result.employer_cost_total += amount
        # ComponentType.REFERENCE: intentionally not summed anywhere. It was already resolved
        # into `context` above so other formulas (e.g. ESIC) can use it, but it isn't paid,
        # isn't a cost, and won't appear on the payslip or CTC totals - purely a calculation helper.

    # --- 4. Ad-hoc one-off entries (e.g. uniform deduction on resignation) ---
    adhoc_entries = (
        db.query(models.AdhocEntry)
        .filter_by(employee_id=employee.id, month=month, year=year)
        .all()
    )
    for entry in adhoc_entries:
        result.lines.append(
            ComputedLine(
                code=f"ADHOC_{entry.id}",
                name=entry.label,
                component_type=entry.entry_type.value,
                amount=entry.amount,
                source="adhoc",
            )
        )
        if entry.entry_type == models.EntryType.EARNING:
            result.gross_earnings += entry.amount
        else:
            result.gross_deductions += entry.amount

    result.gross_earnings = round(result.gross_earnings, 2)
    result.gross_deductions = round(result.gross_deductions, 2)
    result.net_pay = round(result.gross_earnings - result.gross_deductions, 2)
    result.employer_cost_total = round(result.employer_cost_total, 2)
    # CTC = everything the employer pays out for this employee this month:
    # gross earnings (what the employee is paid before their own deductions) + employer-side contributions.
    result.ctc_total = round(result.gross_earnings + result.employer_cost_total, 2)

    return result
