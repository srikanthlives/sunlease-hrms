from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_payroll_or_admin, require_any
from ..formula_engine import compute_payslip, PayrollError
from ..utils.eligibility import is_eligible_for_period, ineligibility_reason

router = APIRouter(prefix="/payroll", tags=["payroll"])


def _serialize_payslip(db: Session, p: models.Payslip, viewer_role: models.UserRole) -> schemas.PayslipOut:
    """
    Employees only ever see their own take-home breakdown (earnings/deductions/net pay).
    Employer-side cost lines (EMPLOYER_CONTRIBUTION) and pure calculation helpers
    (REFERENCE, e.g. a GROSS_SALARY used to compute ESIC) are stripped out for them, along
    with the employer_cost_total / ctc_total figures - those are cost-summary/CTC data,
    visible only to admin & payroll_processor.

    Payments made towards this month's salary (and the resulting balance) ARE shown to
    everyone, including the employee themselves - that's the whole point of tracking them.
    """
    out = schemas.PayslipOut.model_validate(p)

    payments = (
        db.query(models.SalaryPayment)
        .filter_by(employee_id=p.employee_id, month=p.month, year=p.year)
        .order_by(models.SalaryPayment.created_at)
        .all()
    )
    out.payments = [schemas.SalaryPaymentOut.model_validate(pm) for pm in payments]
    out.total_paid = round(sum(pm.amount for pm in payments), 2)
    out.balance = round(p.net_pay - out.total_paid, 2)

    if viewer_role == models.UserRole.EMPLOYEE:
        out.lines = [
            l for l in out.lines
            if l.component_type in (models.ComponentType.EARNING, models.ComponentType.DEDUCTION)
        ]
        out.employer_cost_total = None
        out.ctc_total = None
    return out


def _persist_payslip(db: Session, employee: models.Employee, month: int, year: int, payroll_run_id: int, generated_by: str) -> models.Payslip:
    computation = compute_payslip(db, employee, month, year)

    existing = db.query(models.Payslip).filter_by(employee_id=employee.id, month=month, year=year).first()
    if existing:
        db.query(models.PayslipLine).filter_by(payslip_id=existing.id).delete()
        payslip = existing
        payslip.payroll_run_id = payroll_run_id
    else:
        payslip = models.Payslip(employee_id=employee.id, month=month, year=year, payroll_run_id=payroll_run_id)
        db.add(payslip)
        db.flush()

    payslip.gross_earnings = computation.gross_earnings
    payslip.gross_deductions = computation.gross_deductions
    payslip.net_pay = computation.net_pay
    payslip.employer_cost_total = computation.employer_cost_total
    payslip.ctc_total = computation.ctc_total
    payslip.template_no = computation.template_no
    payslip.present_days = computation.present_days
    payslip.total_days = computation.total_days
    payslip.generated_by = generated_by

    db.flush()
    for line in computation.lines:
        db.add(models.PayslipLine(
            payslip_id=payslip.id,
            component_code=line.code,
            component_name=line.name,
            component_type=line.component_type,
            amount=line.amount,
            source=line.source,
        ))
    db.flush()
    return payslip


def _cleanup_stale_payslips(db: Session, month: int, year: int) -> list[str]:
    """
    Remove any payslip already on record for this month/year where the employee is no
    longer eligible for this period (e.g. their last working day turned out to be before
    this month, but a payslip had already been generated before that was known/entered).
    Runs automatically at the start of every payroll run for the period.
    """
    removed = []
    existing = db.query(models.Payslip).filter_by(month=month, year=year).all()
    for ps in existing:
        emp = db.query(models.Employee).get(ps.employee_id)
        if emp and not is_eligible_for_period(emp, month, year):
            reason = ineligibility_reason(emp, month, year) or "no longer eligible"
            db.query(models.PayslipLine).filter_by(payslip_id=ps.id).delete()
            db.delete(ps)
            removed.append(f"{emp.employee_code}: removed stale payslip ({reason})")
    if removed:
        db.flush()
    return removed


@router.post("/run", response_model=schemas.RunPayrollResult)
def run_payroll(payload: schemas.RunPayrollRequest, db: Session = Depends(get_db), current_user: models.User = Depends(require_payroll_or_admin)):
    removed_stale = _cleanup_stale_payslips(db, payload.month, payload.year)

    # Eligibility is date-driven (date_of_joining / date_of_leaving), not the `status` field -
    # someone whose last working day was this month still gets paid for it; someone whose
    # last working day was before this month is excluded even if their status was never updated.
    candidates_query = db.query(models.Employee)
    if payload.employee_ids:
        candidates_query = candidates_query.filter(models.Employee.id.in_(payload.employee_ids))
    candidates = candidates_query.all()

    eligible = [e for e in candidates if is_eligible_for_period(e, payload.month, payload.year)]
    skipped_ineligible = [
        f"{e.employee_code}: skipped - {ineligibility_reason(e, payload.month, payload.year)}"
        for e in candidates if e not in eligible
    ]

    if not eligible:
        db.commit()  # keep any stale-payslip cleanup even if nothing new can be generated
        raise HTTPException(status_code=400, detail="No employees are eligible for payroll in this period.")

    run = db.query(models.PayrollRun).filter_by(month=payload.month, year=payload.year).first()
    if not run:
        run = models.PayrollRun(month=payload.month, year=payload.year, run_by=current_user.username)
        db.add(run)
        db.flush()

    generated = 0
    failed = list(skipped_ineligible)
    payslips_out = []
    for emp in eligible:
        try:
            payslip = _persist_payslip(db, emp, payload.month, payload.year, run.id, current_user.username)
            generated += 1
            payslips_out.append(payslip)
        except PayrollError as e:
            failed.append(f"{emp.employee_code}: {e}")
        except Exception as e:
            failed.append(f"{emp.employee_code}: unexpected error - {e}")

    db.commit()
    for p in payslips_out:
        db.refresh(p)

    return schemas.RunPayrollResult(
        payroll_run_id=run.id, generated=generated, failed=failed, removed_stale=removed_stale,
        payslips=[_serialize_payslip(db, p, current_user.role) for p in payslips_out],
    )


@router.get("/payslips", response_model=list[schemas.PayslipOut])
def list_payslips(month: int, year: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_any)):
    q = db.query(models.Payslip).filter_by(month=month, year=year)
    if current_user.role == models.UserRole.EMPLOYEE:
        q = q.filter_by(employee_id=current_user.employee_id)
    return [_serialize_payslip(db, p, current_user.role) for p in q.all()]


@router.get("/payslips/{payslip_id}", response_model=schemas.PayslipOut)
def get_payslip(payslip_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_any)):
    p = db.query(models.Payslip).get(payslip_id)
    if not p:
        raise HTTPException(status_code=404, detail="Payslip not found")
    if current_user.role == models.UserRole.EMPLOYEE and p.employee_id != current_user.employee_id:
        raise HTTPException(status_code=403, detail="You may only view your own payslips.")
    return _serialize_payslip(db, p, current_user.role)


@router.get("/employees/{employee_id}/payslips", response_model=list[schemas.PayslipOut])
def get_employee_payslips(employee_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_any)):
    if current_user.role == models.UserRole.EMPLOYEE and current_user.employee_id != employee_id:
        raise HTTPException(status_code=403, detail="You may only view your own payslips.")
    payslips = db.query(models.Payslip).filter_by(employee_id=employee_id).order_by(
        models.Payslip.year.desc(), models.Payslip.month.desc()
    ).all()
    return [_serialize_payslip(db, p, current_user.role) for p in payslips]


@router.post("/preview/{employee_id}")
def preview_payslip(employee_id: int, month: int, year: int, db: Session = Depends(get_db), _=Depends(require_payroll_or_admin)):
    """Compute a payslip without persisting it - useful for admins to sanity-check a template/overrides."""
    emp = db.query(models.Employee).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    try:
        computation = compute_payslip(db, emp, month, year)
    except PayrollError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "gross_earnings": computation.gross_earnings,
        "gross_deductions": computation.gross_deductions,
        "net_pay": computation.net_pay,
        "employer_cost_total": computation.employer_cost_total,
        "ctc_total": computation.ctc_total,
        "template_no": computation.template_no,
        "present_days": computation.present_days,
        "total_days": computation.total_days,
        "warnings": computation.warnings,
        "lines": [line.__dict__ for line in computation.lines],
    }
