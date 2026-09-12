import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.enums import Permission
from app.models.models import (
    AdhocPayEntry, FullFinalSettlement, Payslip, PayslipCostSplit, PayslipLine,
    PayrollRun, ProfessionalTaxSlab, SalaryComponent, SalaryComponentOverride, SalaryStructureComponent,
    SalaryTemplate, SalaryTemplateComponent, StatutoryConfig, User,
)
from app.schemas.payroll import (
    AdhocPayEntryIn, ApplyTemplateIn, PayrollRunIn, ProfessionalTaxSlabIn, SalaryComponentIn,
    SalaryComponentOverrideIn, SalaryStructureComponentEndIn, SalaryStructureComponentIn,
    SalaryTemplateComponentIn, SalaryTemplateIn, StatutoryConfigIn,
)
from app.services import (
    approval_service, audit_service, employee_service, payroll_service, permission_service,
    salary_structure_bulk_import_service,
)

router = APIRouter(prefix="/api/v1/payroll", tags=["payroll"], dependencies=[Depends(get_current_user)])


# ---------------------------------------------------------------------------
# dict helpers
# ---------------------------------------------------------------------------

def _component_dict(c: SalaryComponent) -> dict:
    return {
        "id": c.id, "code": c.code, "name": c.name, "component_type": c.component_type,
        "default_calculation": c.default_calculation, "default_value": c.default_value, "formula": c.formula,
        "sequence": c.sequence, "is_statutory": c.is_statutory, "is_active": c.is_active,
    }


def _structure_dict(s: SalaryStructureComponent) -> dict:
    component = s.component
    return {
        "id": s.id, "episode_id": s.episode_id, "component_id": s.component_id,
        "component_code": component.code if component else None, "component_name": component.name if component else None,
        "component_default_calculation": component.default_calculation if component else None,
        "amount": s.amount, "percentage": s.percentage, "formula": s.formula,
        "effective_from": s.effective_from, "effective_to": s.effective_to,
    }


def _template_dict(t: SalaryTemplate) -> dict:
    return {
        "id": t.id, "code": t.code, "name": t.name,
        "cost_center_id": t.cost_center_id, "cost_center_name": t.cost_center.name if t.cost_center else None,
        "project_id": t.project_id, "project_name": t.project.name if t.project else None,
        "is_active": t.is_active,
    }


def _template_component_dict(c: SalaryTemplateComponent) -> dict:
    component = c.component
    return {
        "id": c.id, "template_id": c.template_id, "component_id": c.component_id,
        "component_code": component.code if component else None, "component_name": component.name if component else None,
        "amount": c.amount, "percentage": c.percentage, "formula": c.formula,
    }


def _run_dict(r: PayrollRun) -> dict:
    return {
        "id": r.id, "cost_center_id": r.cost_center_id, "year": r.year, "month": r.month, "status": r.status,
        "processed_by": r.processed_by.username if r.processed_by else None, "processed_at": r.processed_at,
        "approved_by": r.approved_by.username if r.approved_by else None, "approved_at": r.approved_at,
        "locked_at": r.locked_at,
    }


def _payslip_summary_dict(p: Payslip) -> dict:
    episode = p.episode
    return {
        "id": p.id, "run_id": p.run_id, "episode_id": p.episode_id,
        "employee_number": episode.employee_number if episode else None,
        "first_name": episode.employee.first_name if episode and episode.employee else None,
        "last_name": episode.employee.last_name if episode and episode.employee else None,
        "present_days": p.present_days, "paid_leave_days": p.paid_leave_days, "lop_days": p.lop_days,
        "gross_earnings": p.gross_earnings, "gross_deductions": p.gross_deductions,
        "net_pay": p.net_pay, "employer_cost_total": p.employer_cost_total,
        "additional_pay": p.additional_pay, "total_payable": p.total_payable,
    }


def _statutory_config_dict(c: StatutoryConfig) -> dict:
    return {
        "id": c.id, "effective_from": c.effective_from, "effective_to": c.effective_to,
        "pf_employee_rate": c.pf_employee_rate, "pf_employer_rate": c.pf_employer_rate, "pf_wage_ceiling": c.pf_wage_ceiling,
        "eps_rate": c.eps_rate, "eps_wage_ceiling": c.eps_wage_ceiling,
        "esi_employee_rate": c.esi_employee_rate, "esi_employer_rate": c.esi_employer_rate, "esi_wage_ceiling": c.esi_wage_ceiling,
        "gratuity_days_per_year": c.gratuity_days_per_year, "gratuity_divisor": c.gratuity_divisor,
        "lwf_employee_amount": c.lwf_employee_amount, "lwf_employer_amount": c.lwf_employer_amount, "lwf_frequency": c.lwf_frequency,
    }


def _pt_slab_dict(s: ProfessionalTaxSlab) -> dict:
    return {
        "id": s.id, "state": s.state, "min_gross": s.min_gross, "max_gross": s.max_gross,
        "monthly_amount": s.monthly_amount, "is_active": s.is_active,
    }


def _adhoc_dict(a: AdhocPayEntry) -> dict:
    return {
        "id": a.id, "episode_id": a.episode_id, "year": a.year, "month": a.month, "label": a.label,
        "amount": a.amount, "is_earning": a.is_earning, "remarks": a.remarks,
        "created_by": a.created_by.username if a.created_by else None,
    }


def _settlement_dict(s: FullFinalSettlement) -> dict:
    return {
        "id": s.id, "episode_id": s.episode_id, "separation_id": s.separation_id,
        "leave_encashment_days": s.leave_encashment_days, "leave_encashment_amount": s.leave_encashment_amount,
        "gratuity_years_of_service": s.gratuity_years_of_service, "gratuity_amount": s.gratuity_amount,
        "notice_pay_recovery": s.notice_pay_recovery, "other_dues": s.other_dues, "net_payable": s.net_payable,
        "status": s.status, "processed_at": s.processed_at,
    }


def _get_episode_or_404(db: Session, episode_id: int):
    from app.models.models import EmploymentEpisode
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == episode_id).first()
    if not episode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee record not found")
    return episode


def _check_scope(db: Session, user: User, episode):
    cc_id = approval_service.current_cost_center_id(db, episode.id)
    if not permission_service.can_see_cost_center(db, user, cc_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This employee is outside your Cost Center scope")


# ---------------------------------------------------------------------------
# Salary Component master (write gated on PAYROLL_PROCESS - judgment call:
# there's no dedicated "payroll admin" permission code, and HR_STAFF who
# processes payroll is the natural owner of the component master too).
# ---------------------------------------------------------------------------

@router.get("/components", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def list_components(db: Session = Depends(get_db)):
    rows = db.query(SalaryComponent).order_by(SalaryComponent.sequence, SalaryComponent.name).all()
    return [_component_dict(c) for c in rows]


@router.post("/components", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def create_component(payload: SalaryComponentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.query(SalaryComponent).filter(SalaryComponent.code == payload.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Component code already exists")
    obj = SalaryComponent(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit_service.record(db, "SALARY_COMPONENT", obj.id, "CREATE", user)
    db.commit()
    db.refresh(obj)
    return _component_dict(obj)


@router.put("/components/{component_id}", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def update_component(component_id: int, payload: SalaryComponentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.query(SalaryComponent).filter(SalaryComponent.id == component_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Salary component not found")
    dupe = db.query(SalaryComponent).filter(SalaryComponent.code == payload.code, SalaryComponent.id != component_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Component code already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    audit_service.record(db, "SALARY_COMPONENT", obj.id, "UPDATE", user)
    db.commit()
    db.refresh(obj)
    return _component_dict(obj)


# ---------------------------------------------------------------------------
# Statutory config + Professional Tax slabs
# ---------------------------------------------------------------------------

@router.get("/statutory-config", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def get_statutory_config(db: Session = Depends(get_db)):
    try:
        config = payroll_service.active_statutory_config(db, date.today())
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return _statutory_config_dict(config)


@router.post("/statutory-config", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def set_statutory_config(payload: StatutoryConfigIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Closes the previously-active StatutoryConfig row (effective_to =
    new effective_from - 1 day) before inserting the new one, same
    close-prior-row pattern as OrgAssignment/SalaryStructureComponent -
    keeps one active config row at a time while preserving rate history."""
    prior = (
        db.query(StatutoryConfig)
        .filter(StatutoryConfig.effective_to.is_(None))
        .order_by(StatutoryConfig.effective_from.desc())
        .first()
    )
    if prior and prior.effective_from < payload.effective_from:
        prior.effective_to = payload.effective_from - timedelta(days=1)
        db.add(prior)
    obj = StatutoryConfig(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit_service.record(db, "STATUTORY_CONFIG", obj.id, "CREATE", user)
    db.commit()
    db.refresh(obj)
    return _statutory_config_dict(obj)


@router.get("/pt-slabs", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def list_pt_slabs(db: Session = Depends(get_db)):
    rows = db.query(ProfessionalTaxSlab).order_by(ProfessionalTaxSlab.state, ProfessionalTaxSlab.min_gross).all()
    return [_pt_slab_dict(s) for s in rows]


@router.post("/pt-slabs", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def create_pt_slab(payload: ProfessionalTaxSlabIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = ProfessionalTaxSlab(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit_service.record(db, "PT_SLAB", obj.id, "CREATE", user)
    db.commit()
    db.refresh(obj)
    return _pt_slab_dict(obj)


@router.put("/pt-slabs/{slab_id}", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def update_pt_slab(slab_id: int, payload: ProfessionalTaxSlabIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.query(ProfessionalTaxSlab).filter(ProfessionalTaxSlab.id == slab_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Professional Tax slab not found")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    audit_service.record(db, "PT_SLAB", obj.id, "UPDATE", user)
    db.commit()
    db.refresh(obj)
    return _pt_slab_dict(obj)


# ---------------------------------------------------------------------------
# Salary structure
# ---------------------------------------------------------------------------

@router.post("/structure", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def assign_structure_component(payload: SalaryStructureComponentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode_or_404(db, payload.episode_id)
    _check_scope(db, user, episode)
    component = db.query(SalaryComponent).filter(SalaryComponent.id == payload.component_id).first()
    if not component:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Salary component not found")
    try:
        row = payroll_service.set_salary_structure_component(
            db, episode.id, payload.component_id, payload.amount, payload.percentage, payload.effective_from, user,
            formula=payload.formula,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(row)
    return _structure_dict(row)


@router.get("/structure/{episode_id}", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def get_structure(episode_id: int, as_of: str | None = Query(None), history: bool = Query(False), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import datetime as dt
    episode = _get_episode_or_404(db, episode_id)
    _check_scope(db, user, episode)
    if history:
        rows = payroll_service.salary_structure_history(db, episode_id)
    else:
        as_of_date = dt.date.fromisoformat(as_of) if as_of else dt.date.today()
        rows = payroll_service.active_salary_structure(db, episode_id, as_of_date)
    return [_structure_dict(r) for r in rows]


@router.post("/structure/{row_id}/end", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def end_structure_component(row_id: int, payload: SalaryStructureComponentEndIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(SalaryStructureComponent).filter(SalaryStructureComponent.id == row_id).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Salary structure row not found")
    episode = _get_episode_or_404(db, row.episode_id)
    _check_scope(db, user, episode)
    try:
        payroll_service.end_salary_structure_component(db, row_id, payload.effective_to, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(row)
    return _structure_dict(row)


@router.get("/structure-bulk-upload-template", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def download_structure_template(db: Session = Depends(get_db)):
    wb = salary_structure_bulk_import_service.build_structure_template_workbook(db)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=hrms_salary_structure_bulk_upload_template.xlsx"},
    )


@router.post("/structure-bulk-upload", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def upload_structure_bulk(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    content = file.file.read()
    result = salary_structure_bulk_import_service.import_structure_workbook(db, content, user)
    db.commit()
    return result


# ---------------------------------------------------------------------------
# Salary templates (reusable structure blueprints, scoped to a Cost
# Center and/or Project, or global when both are null)
# ---------------------------------------------------------------------------

@router.get("/templates", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def list_templates(
    cost_center_id: int | None = Query(None), project_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    if cost_center_id is not None or project_id is not None:
        rows = payroll_service.matching_templates(db, cost_center_id, project_id)
    else:
        rows = db.query(SalaryTemplate).filter(SalaryTemplate.is_active.is_(True)).all()
    return [_template_dict(t) for t in rows]


@router.post("/templates", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def create_template(payload: SalaryTemplateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.query(SalaryTemplate).filter(SalaryTemplate.code == payload.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Template code already exists")
    obj = SalaryTemplate(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit_service.record(db, "SALARY_TEMPLATE", obj.id, "CREATE", user)
    db.commit()
    db.refresh(obj)
    return _template_dict(obj)


@router.put("/templates/{template_id}", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def update_template(template_id: int, payload: SalaryTemplateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.query(SalaryTemplate).filter(SalaryTemplate.id == template_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Salary template not found")
    dupe = db.query(SalaryTemplate).filter(SalaryTemplate.code == payload.code, SalaryTemplate.id != template_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Template code already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    audit_service.record(db, "SALARY_TEMPLATE", obj.id, "UPDATE", user)
    db.commit()
    db.refresh(obj)
    return _template_dict(obj)


@router.get("/templates/{template_id}/components", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def list_template_components(template_id: int, db: Session = Depends(get_db)):
    rows = db.query(SalaryTemplateComponent).filter(SalaryTemplateComponent.template_id == template_id).all()
    return [_template_component_dict(c) for c in rows]


@router.post("/templates/{template_id}/components", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def add_template_component(template_id: int, payload: SalaryTemplateComponentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    template = db.query(SalaryTemplate).filter(SalaryTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Salary template not found")
    existing = db.query(SalaryTemplateComponent).filter(
        SalaryTemplateComponent.template_id == template_id, SalaryTemplateComponent.component_id == payload.component_id,
    ).first()
    if existing:
        existing.amount = payload.amount
        existing.percentage = payload.percentage
        existing.formula = payload.formula
        db.add(existing)
        audit_service.record(db, "SALARY_TEMPLATE_COMPONENT", existing.id, "UPDATE", user)
        db.commit()
        db.refresh(existing)
        return _template_component_dict(existing)
    obj = SalaryTemplateComponent(template_id=template_id, **payload.model_dump())
    db.add(obj)
    db.flush()
    audit_service.record(db, "SALARY_TEMPLATE_COMPONENT", obj.id, "CREATE", user)
    db.commit()
    db.refresh(obj)
    return _template_component_dict(obj)


@router.delete("/templates/{template_id}/components/{component_row_id}", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def remove_template_component(template_id: int, component_row_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.query(SalaryTemplateComponent).filter(
        SalaryTemplateComponent.id == component_row_id, SalaryTemplateComponent.template_id == template_id,
    ).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template component not found")
    audit_service.record(db, "SALARY_TEMPLATE_COMPONENT", obj.id, "DELETE", user)
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.get("/templates/{template_id}/sample-payslip", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def preview_template_payslip(template_id: int, db: Session = Depends(get_db)):
    """Illustrative payslip for a fully-worked 31-day month, computed from
    the template's component definitions alone (formulas/percentages
    resolved, no proration). Excludes statutory PF/ESI/PT/LWF, which
    depend on a specific employee's eligibility - those only appear once
    the template is applied to a real employee and payroll is processed."""
    template = db.query(SalaryTemplate).filter(SalaryTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Salary template not found")
    rows = db.query(SalaryTemplateComponent).filter(SalaryTemplateComponent.template_id == template_id).all()
    preview_rows = [
        {
            "code": r.component.code, "name": r.component.name, "component_type": r.component.component_type,
            "amount": r.amount, "percentage": r.percentage, "formula": r.formula or r.component.formula,
        }
        for r in rows if r.component
    ]
    return payroll_service.preview_component_amounts(preview_rows)


@router.get("/structure/{episode_id}/sample-payslip", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def preview_structure_payslip(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Same as the template preview, but for an employee's currently
    active salary structure - a "what would this look like for a fully
    worked 31-day month" view before running real payroll."""
    episode = _get_episode_or_404(db, episode_id)
    _check_scope(db, user, episode)
    rows = payroll_service.active_salary_structure(db, episode_id, date.today())
    preview_rows = [
        {
            "code": r.component.code, "name": r.component.name, "component_type": r.component.component_type,
            "amount": r.amount, "percentage": r.percentage, "formula": r.formula or r.component.formula,
        }
        for r in rows if r.component and not r.component.is_statutory
    ]
    return payroll_service.preview_component_amounts(preview_rows)


@router.post("/structure/apply-template", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def apply_template_to_structure(payload: ApplyTemplateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Applies a (possibly hand-edited) copy of the template's component
    rows to the employee's structure - the frontend fetches the template,
    lets the user change amounts/percentages, then submits the final
    values here rather than the template being applied verbatim."""
    episode = _get_episode_or_404(db, payload.episode_id)
    _check_scope(db, user, episode)
    template = db.query(SalaryTemplate).filter(SalaryTemplate.id == payload.template_id).first()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Salary template not found")
    applied, errors = payroll_service.apply_template(
        db, payload.episode_id, payload.effective_from,
        [c.model_dump() for c in payload.components], user,
    )
    db.commit()
    return {"applied": len(applied), "errors": errors}


# ---------------------------------------------------------------------------
# Salary component overrides (one-month exception, e.g. "Group Insurance
# is normally Rs.50 but wasn't collected this month - use 0 instead")
# ---------------------------------------------------------------------------

def _override_dict(o: SalaryComponentOverride) -> dict:
    component = o.component
    return {
        "id": o.id, "episode_id": o.episode_id, "component_id": o.component_id,
        "component_code": component.code if component else None, "component_name": component.name if component else None,
        "year": o.year, "month": o.month, "amount": o.amount, "remarks": o.remarks,
        "created_by": o.created_by.username if o.created_by else None, "created_at": o.created_at,
    }


@router.get("/overrides/{episode_id}", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def get_overrides(episode_id: int, year: int = Query(...), month: int = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode_or_404(db, episode_id)
    _check_scope(db, user, episode)
    rows = payroll_service.list_overrides(db, episode_id, year, month)
    return [_override_dict(o) for o in rows]


@router.post("/overrides", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def set_override(payload: SalaryComponentOverrideIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode_or_404(db, payload.episode_id)
    _check_scope(db, user, episode)
    component = db.query(SalaryComponent).filter(SalaryComponent.id == payload.component_id).first()
    if not component:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Salary component not found")
    row = payroll_service.set_override(db, payload.episode_id, payload.component_id, payload.year, payload.month, payload.amount, payload.remarks, user)
    db.commit()
    db.refresh(row)
    return _override_dict(row)


@router.delete("/overrides/{override_id}", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def remove_override(override_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        payroll_service.delete_override(db, override_id, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Payroll run
# ---------------------------------------------------------------------------

@router.post("/run", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def run_payroll(payload: PayrollRunIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not permission_service.can_see_cost_center(db, user, payload.cost_center_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This Cost Center is outside your scope")
    try:
        run, errors = payroll_service.process_payroll_run(db, payload.cost_center_id, payload.year, payload.month, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(run)
    return {"run": _run_dict(run), "errors": errors}


@router.get("/runs", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def list_runs(
    cost_center_id: int | None = Query(None), year: int | None = Query(None), month: int | None = Query(None),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    query = db.query(PayrollRun)
    if cost_center_id is not None:
        query = query.filter(PayrollRun.cost_center_id == cost_center_id)
    if year is not None:
        query = query.filter(PayrollRun.year == year)
    if month is not None:
        query = query.filter(PayrollRun.month == month)
    rows = query.order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all()
    rows = [r for r in rows if permission_service.can_see_cost_center(db, user, r.cost_center_id)]
    return [_run_dict(r) for r in rows]


@router.post("/runs/{run_id}/approve", dependencies=[Depends(require_permission(Permission.PAYROLL_APPROVE))])
def approve_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        run = payroll_service.approve_payroll_run(db, run_id, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(run)
    return _run_dict(run)


@router.post("/runs/{run_id}/lock", dependencies=[Depends(require_permission(Permission.PAYROLL_LOCK))])
def lock_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        run = payroll_service.lock_payroll_run(db, run_id, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(run)
    return _run_dict(run)


# ---------------------------------------------------------------------------
# Payslips
# ---------------------------------------------------------------------------

@router.get("/payslips", dependencies=[Depends(require_permission(Permission.PAYSLIP_VIEW))])
def list_payslips_aggregate(
    cost_center_id: int | None = Query(None), year: int = Query(...), month: int = Query(...),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Aggregate list mirroring attendance.list_records_aggregate: for
    every episode in scope for this Cost Center/month, returns its Payslip
    (if the run has been processed) or None."""
    import calendar
    import datetime as dt

    _, last_day = calendar.monthrange(year, month)
    month_start, month_end = dt.date(year, month, 1), dt.date(year, month, last_day)
    episodes = employee_service.episodes_in_cost_center_during(db, cost_center_id, month_start, month_end)
    episodes = [e for e in episodes if permission_service.can_see_cost_center(db, user, approval_service.current_cost_center_id(db, e.id))]
    episode_ids = [e.id for e in episodes]

    run = db.query(PayrollRun).filter(PayrollRun.cost_center_id == cost_center_id, PayrollRun.year == year, PayrollRun.month == month).first()
    payslips_by_episode = {}
    if run and episode_ids:
        rows = db.query(Payslip).filter(Payslip.run_id == run.id, Payslip.episode_id.in_(episode_ids)).all()
        payslips_by_episode = {p.episode_id: p for p in rows}

    result = []
    for e in episodes:
        payslip = payslips_by_episode.get(e.id)
        result.append({
            "episode_id": e.id,
            "employee_number": e.employee_number,
            "first_name": e.employee.first_name,
            "last_name": e.employee.last_name,
            "payslip": _payslip_summary_dict(payslip) if payslip else None,
        })
    return {"run": _run_dict(run) if run else None, "employees": result}


def build_payslip_detail(db: Session, payslip: Payslip) -> dict:
    """Assembles the full payslip-detail shape (summary + lines + cost
    splits). Caller is responsible for any scope/ownership check."""
    lines = db.query(PayslipLine).filter(PayslipLine.payslip_id == payslip.id).all()
    splits = db.query(PayslipCostSplit).filter(PayslipCostSplit.payslip_id == payslip.id).all()

    return {
        **_payslip_summary_dict(payslip),
        "generated_at": payslip.generated_at,
        "lines": [
            {"component_code": l.component_code, "component_name": l.component_name, "component_type": l.component_type, "amount": l.amount}
            for l in lines
        ],
        "cost_splits": [
            {"cost_center_id": s.cost_center_id, "project_id": s.project_id, "percentage": s.percentage, "amount": s.amount}
            for s in splits
        ],
    }


@router.get("/payslips/{payslip_id}", dependencies=[Depends(require_permission(Permission.PAYSLIP_VIEW))])
def get_payslip_detail(payslip_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not payslip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payslip not found")
    episode = payslip.episode
    _check_scope(db, user, episode)
    return build_payslip_detail(db, payslip)


# ---------------------------------------------------------------------------
# Ad-hoc pay entries
# ---------------------------------------------------------------------------

@router.get("/adhoc-entries", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def list_adhoc_entries(
    episode_id: int | None = Query(None), year: int | None = Query(None), month: int | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(AdhocPayEntry)
    if episode_id is not None:
        query = query.filter(AdhocPayEntry.episode_id == episode_id)
    if year is not None:
        query = query.filter(AdhocPayEntry.year == year)
    if month is not None:
        query = query.filter(AdhocPayEntry.month == month)
    rows = query.order_by(AdhocPayEntry.year.desc(), AdhocPayEntry.month.desc()).all()
    return [_adhoc_dict(a) for a in rows]


@router.post("/adhoc-entries", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def create_adhoc_entry(payload: AdhocPayEntryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode_or_404(db, payload.episode_id)
    _check_scope(db, user, episode)
    obj = AdhocPayEntry(**payload.model_dump(), created_by_id=user.id)
    db.add(obj)
    db.flush()
    audit_service.record(db, "ADHOC_PAY_ENTRY", obj.id, "CREATE", user, new_value=f"{payload.label}={payload.amount}")
    db.commit()
    db.refresh(obj)
    return _adhoc_dict(obj)


@router.put("/adhoc-entries/{entry_id}", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def update_adhoc_entry(entry_id: int, payload: AdhocPayEntryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.query(AdhocPayEntry).filter(AdhocPayEntry.id == entry_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ad-hoc pay entry not found")
    episode = _get_episode_or_404(db, payload.episode_id)
    _check_scope(db, user, episode)
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    audit_service.record(db, "ADHOC_PAY_ENTRY", obj.id, "UPDATE", user)
    db.commit()
    db.refresh(obj)
    return _adhoc_dict(obj)


@router.delete("/adhoc-entries/{entry_id}", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def delete_adhoc_entry(entry_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Ad-hoc entries are one-off, point-in-time corrections (not
    effective-dated history like OrgAssignment/CostAllocation), so a
    genuine delete - not a deactivate - is appropriate here; a payroll run
    already processed against a since-deleted entry is unaffected since
    its PayslipLine was already written."""
    obj = db.query(AdhocPayEntry).filter(AdhocPayEntry.id == entry_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ad-hoc pay entry not found")
    episode = _get_episode_or_404(db, obj.episode_id)
    _check_scope(db, user, episode)
    audit_service.record(db, "ADHOC_PAY_ENTRY", obj.id, "DELETE", user, old_value=f"{obj.label}={obj.amount}")
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.get("/adhoc-entries-bulk-upload-template", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def download_adhoc_template():
    wb = salary_structure_bulk_import_service.build_adhoc_template_workbook()
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=hrms_adhoc_pay_entries_bulk_upload_template.xlsx"},
    )


@router.post("/adhoc-entries-bulk-upload", dependencies=[Depends(require_permission(Permission.PAYROLL_PROCESS))])
def upload_adhoc_bulk(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    content = file.file.read()
    result = salary_structure_bulk_import_service.import_adhoc_workbook(db, content, user)
    db.commit()
    return result


# ---------------------------------------------------------------------------
# Full & Final Settlement (payroll side)
# ---------------------------------------------------------------------------

@router.post("/full-final/{episode_id}/process", dependencies=[Depends(require_permission(Permission.FNF_PROCESS))])
def process_full_final(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode_or_404(db, episode_id)
    _check_scope(db, user, episode)
    try:
        settlement = payroll_service.process_full_final_settlement(db, episode_id, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(settlement)
    return _settlement_dict(settlement)


@router.get("/full-final/{episode_id}", dependencies=[Depends(require_permission(Permission.PAYROLL_VIEW))])
def get_full_final(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode_or_404(db, episode_id)
    _check_scope(db, user, episode)
    settlement = db.query(FullFinalSettlement).filter(FullFinalSettlement.episode_id == episode_id).first()
    if not settlement:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No Full & Final Settlement found for this employee")
    return _settlement_dict(settlement)
