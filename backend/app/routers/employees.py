from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_admin, require_payroll_or_admin, require_any, get_current_user
from ..utils.excel import parse_employee_upload
from ..utils.eligibility import is_eligible_for_period

router = APIRouter(prefix="/employees", tags=["employees"])


def _scope_check_self_or_staff(current_user: models.User, employee_id: int):
    """Employees may only access their own record; admin/payroll can access any."""
    if current_user.role == models.UserRole.EMPLOYEE and current_user.employee_id != employee_id:
        raise HTTPException(status_code=403, detail="You may only access your own employee record.")


@router.get("", response_model=list[schemas.EmployeeOut])
def list_employees(db: Session = Depends(get_db), current_user: models.User = Depends(require_any)):
    if current_user.role == models.UserRole.EMPLOYEE:
        return db.query(models.Employee).filter_by(id=current_user.employee_id).all()
    return db.query(models.Employee).all()


@router.get("/eligible", response_model=list[schemas.EmployeeOut])
def list_eligible_employees(month: int, year: int, db: Session = Depends(get_db), _=Depends(require_payroll_or_admin)):
    """
    Employees eligible for payroll in a given month/year, based on date_of_joining /
    date_of_leaving - NOT the `status` field. This is what "Run Payroll" and its employee
    picker use, so someone whose last working day was in April still shows up for April's
    run and disappears from May's, regardless of whether their status was ever updated.
    """
    return [e for e in db.query(models.Employee).all() if is_eligible_for_period(e, month, year)]


@router.get("/{employee_id}", response_model=schemas.EmployeeOut)
def get_employee(employee_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_any)):
    _scope_check_self_or_staff(current_user, employee_id)
    emp = db.query(models.Employee).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.post("/upload", response_model=schemas.BulkUploadResult)
async def upload_employees(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(require_admin)):
    """
    Bulk-create/update employees from an Excel file.
    Required columns: employee_code, first_name.
    Optional: last_name, email, phone, department, designation, location, date_of_joining,
    template_no (assigns the matching template as the employee's default), bank_name,
    bank_account, ifsc, pan, uan.
    Existing employees (matched by employee_code) are updated; new codes are created.
    """
    content = await file.read()
    try:
        rows = parse_employee_upload(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    inserted, updated, errors = 0, 0, []
    for row in rows:
        template_id = None
        if row["template_no"]:
            template = db.query(models.SalaryTemplate).filter_by(template_no=row["template_no"]).first()
            if not template:
                errors.append(f"{row['employee_code']}: template_no '{row['template_no']}' not found - left unassigned")
            else:
                template_id = template.id

        if row["email"] and db.query(models.Employee).filter(
            models.Employee.email == row["email"], models.Employee.employee_code != row["employee_code"]
        ).first():
            errors.append(f"{row['employee_code']}: email '{row['email']}' already used by another employee - skipped email")
            row["email"] = None

        existing = db.query(models.Employee).filter_by(employee_code=row["employee_code"]).first()
        if existing:
            existing.first_name = row["first_name"]
            existing.last_name = row["last_name"]
            if row["email"]:
                existing.email = row["email"]
            existing.phone = row["phone"] or existing.phone
            existing.department = row["department"] or existing.department
            existing.designation = row["designation"] or existing.designation
            existing.location = row["location"] or existing.location
            existing.date_of_joining = row["date_of_joining"] or existing.date_of_joining
            existing.bank_name = row["bank_name"] or existing.bank_name
            existing.bank_account = row["bank_account"] or existing.bank_account
            existing.ifsc = row["ifsc"] or existing.ifsc
            existing.pan = row["pan"] or existing.pan
            existing.uan = row["uan"] or existing.uan
            existing.pf_eligible = row["pf_eligible"]
            existing.eps_eligible = row["eps_eligible"]
            existing.esi_number = row["esi_number"] or existing.esi_number
            existing.esi_eligible = row["esi_eligible"]
            existing.mediclaim_policy_no = row["mediclaim_policy_no"] or existing.mediclaim_policy_no
            existing.mediclaim_eligible = row["mediclaim_eligible"]
            if template_id:
                existing.template_id = template_id
            updated += 1
        else:
            db.add(models.Employee(
                employee_code=row["employee_code"], first_name=row["first_name"], last_name=row["last_name"],
                email=row["email"], phone=row["phone"], department=row["department"], designation=row["designation"],
                location=row["location"], date_of_joining=row["date_of_joining"], template_id=template_id,
                bank_name=row["bank_name"], bank_account=row["bank_account"], ifsc=row["ifsc"],
                pan=row["pan"], uan=row["uan"], pf_eligible=row["pf_eligible"], eps_eligible=row["eps_eligible"],
                esi_number=row["esi_number"], esi_eligible=row["esi_eligible"], mediclaim_policy_no=row["mediclaim_policy_no"],
                mediclaim_eligible=row["mediclaim_eligible"],
            ))
            inserted += 1

    db.commit()
    return schemas.BulkUploadResult(inserted=inserted, updated=updated, errors=errors)


@router.post("", response_model=schemas.EmployeeOut)
def create_employee(payload: schemas.EmployeeCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(models.Employee).filter_by(employee_code=payload.employee_code).first():
        raise HTTPException(status_code=400, detail="Employee code already exists")
    if payload.email and db.query(models.Employee).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="Email already in use by another employee")
    if payload.template_id and not db.query(models.SalaryTemplate).get(payload.template_id):
        raise HTTPException(status_code=400, detail="Salary template not found")
    emp = models.Employee(**payload.model_dump())
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@router.put("/{employee_id}", response_model=schemas.EmployeeOut)
def update_employee(employee_id: int, payload: schemas.EmployeeUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    emp = db.query(models.Employee).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    updates = payload.model_dump(exclude_unset=True)

    if "employee_code" in updates and updates["employee_code"] != emp.employee_code:
        if db.query(models.Employee).filter(
            models.Employee.employee_code == updates["employee_code"], models.Employee.id != employee_id
        ).first():
            raise HTTPException(status_code=400, detail="Employee code already in use by another employee")

    if "email" in updates and updates["email"] and updates["email"] != emp.email:
        if db.query(models.Employee).filter(
            models.Employee.email == updates["email"], models.Employee.id != employee_id
        ).first():
            raise HTTPException(status_code=400, detail="Email already in use by another employee")

    if "template_id" in updates and updates["template_id"] and not db.query(models.SalaryTemplate).get(updates["template_id"]):
        raise HTTPException(status_code=400, detail="Salary template not found")

    for k, v in updates.items():
        setattr(emp, k, v)
    db.commit()
    db.refresh(emp)
    return emp


@router.post("/{employee_id}/assign-template/{template_id}", response_model=schemas.EmployeeOut)
def assign_template(employee_id: int, template_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Sets the employee's default/fallback template (used for any period with no dated assignment)."""
    emp = db.query(models.Employee).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    template = db.query(models.SalaryTemplate).get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    emp.template_id = template_id
    db.commit()
    db.refresh(emp)
    return emp


@router.get("/{employee_id}/template-assignments", response_model=list[schemas.TemplateAssignmentOut])
def list_template_assignments(employee_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_any)):
    _scope_check_self_or_staff(current_user, employee_id)
    return (
        db.query(models.EmployeeTemplateAssignment)
        .filter_by(employee_id=employee_id)
        .order_by(models.EmployeeTemplateAssignment.effective_year.desc(), models.EmployeeTemplateAssignment.effective_month.desc())
        .all()
    )


@router.post("/{employee_id}/template-assignments", response_model=schemas.TemplateAssignmentOut)
def create_template_assignment(employee_id: int, payload: schemas.TemplateAssignmentIn, db: Session = Depends(get_db), _=Depends(require_admin)):
    """
    Attach a salary template to an employee effective from a given month/year. This lets a
    template change over time - e.g. Jan 2026 -> Template A, Mar 2026 -> Template B: payroll
    for Jan/Feb 2026 uses A, payroll from Mar 2026 onward uses B, until a later assignment
    (e.g. Mar 2027 -> Template C) overrides it again from that point forward.
    """
    emp = db.query(models.Employee).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if not (1 <= payload.effective_month <= 12):
        raise HTTPException(status_code=400, detail="effective_month must be between 1 and 12")
    template = db.query(models.SalaryTemplate).get(payload.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    existing = db.query(models.EmployeeTemplateAssignment).filter_by(
        employee_id=employee_id, effective_year=payload.effective_year, effective_month=payload.effective_month,
    ).first()
    if existing:
        existing.template_id = payload.template_id
        db.commit()
        db.refresh(existing)
        return existing

    assignment = models.EmployeeTemplateAssignment(
        employee_id=employee_id, template_id=payload.template_id,
        effective_month=payload.effective_month, effective_year=payload.effective_year,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{employee_id}/template-assignments/{assignment_id}")
def delete_template_assignment(employee_id: int, assignment_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    assignment = db.query(models.EmployeeTemplateAssignment).filter_by(id=assignment_id, employee_id=employee_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(assignment)
    db.commit()
    return {"detail": "Assignment deleted"}


@router.delete("/{employee_id}")
def delete_employee(employee_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    emp = db.query(models.Employee).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Cascade-remove everything tied to this employee so the delete doesn't hit FK errors.
    payslip_ids = [p.id for p in db.query(models.Payslip.id).filter_by(employee_id=employee_id).all()]
    if payslip_ids:
        db.query(models.PayslipLine).filter(models.PayslipLine.payslip_id.in_(payslip_ids)).delete(synchronize_session=False)
        db.query(models.Payslip).filter(models.Payslip.id.in_(payslip_ids)).delete(synchronize_session=False)
    db.query(models.MonthlyVariableInput).filter_by(employee_id=employee_id).delete(synchronize_session=False)
    db.query(models.Attendance).filter_by(employee_id=employee_id).delete(synchronize_session=False)
    db.query(models.AdhocEntry).filter_by(employee_id=employee_id).delete(synchronize_session=False)
    db.query(models.EmployeeTemplateAssignment).filter_by(employee_id=employee_id).delete(synchronize_session=False)
    db.query(models.User).filter_by(employee_id=employee_id).delete(synchronize_session=False)

    db.delete(emp)
    db.commit()
    return {"detail": "Employee and all related records deleted"}
