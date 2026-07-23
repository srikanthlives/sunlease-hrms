from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_payroll_or_admin, require_any
from ..utils.excel import parse_variable_upload

router = APIRouter(prefix="/variable-inputs", tags=["monthly-variable-inputs"])


@router.get("", response_model=list[schemas.VariableInputOut])
def list_variable_inputs(month: int, year: int, employee_id: int | None = None, db: Session = Depends(get_db), _=Depends(require_any)):
    q = db.query(models.MonthlyVariableInput).filter_by(month=month, year=year)
    if employee_id:
        q = q.filter_by(employee_id=employee_id)
    return q.all()


@router.post("", response_model=schemas.VariableInputOut)
def upsert_variable_input(payload: schemas.VariableInputIn, db: Session = Depends(get_db), current_user: models.User = Depends(require_payroll_or_admin)):
    emp = db.query(models.Employee).get(payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    record = db.query(models.MonthlyVariableInput).filter_by(
        employee_id=payload.employee_id, component_code=payload.component_code.upper(),
        month=payload.month, year=payload.year,
    ).first()
    if record:
        record.value = payload.value
        record.remarks = payload.remarks
        record.uploaded_by = current_user.username
    else:
        record = models.MonthlyVariableInput(
            employee_id=payload.employee_id, component_code=payload.component_code.upper(),
            month=payload.month, year=payload.year, value=payload.value,
            remarks=payload.remarks, uploaded_by=current_user.username,
        )
        db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post("/upload", response_model=schemas.BulkUploadResult)
async def upload_variable_inputs(
    month: int, year: int, file: UploadFile = File(...),
    db: Session = Depends(get_db), current_user: models.User = Depends(require_payroll_or_admin),
):
    """
    Bulk-upload monthly variable component values (e.g. performance bonus overrides).
    Excel columns: employee_code | component_code | value | remarks (optional).
    Uploaded values OVERRIDE the template's default_value for that employee/month only.
    """
    content = await file.read()
    try:
        rows = parse_variable_upload(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    inserted, updated, errors = 0, 0, []
    for row in rows:
        emp = db.query(models.Employee).filter_by(employee_code=row["employee_code"]).first()
        if not emp:
            errors.append(f"Unknown employee_code '{row['employee_code']}'")
            continue

        # Validate the component exists (as a variable component) on the employee's template.
        comp = None
        if emp.template_id:
            comp = db.query(models.SalaryComponent).filter_by(
                template_id=emp.template_id, code=row["component_code"]
            ).first()
        if not comp:
            errors.append(f"Component '{row['component_code']}' not found on template for {row['employee_code']}")
            continue
        if not comp.is_variable:
            errors.append(f"Component '{row['component_code']}' is not marked variable; cannot override for {row['employee_code']}")
            continue

        record = db.query(models.MonthlyVariableInput).filter_by(
            employee_id=emp.id, component_code=row["component_code"], month=month, year=year
        ).first()
        if record:
            record.value = row["value"]
            record.remarks = row["remarks"]
            record.uploaded_by = current_user.username
            updated += 1
        else:
            db.add(models.MonthlyVariableInput(
                employee_id=emp.id, component_code=row["component_code"], month=month, year=year,
                value=row["value"], remarks=row["remarks"], uploaded_by=current_user.username,
            ))
            inserted += 1
    db.commit()
    return schemas.BulkUploadResult(inserted=inserted, updated=updated, errors=errors)


@router.delete("/{record_id}")
def delete_variable_input(record_id: int, db: Session = Depends(get_db), _=Depends(require_payroll_or_admin)):
    record = db.query(models.MonthlyVariableInput).get(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Override record not found")
    db.delete(record)
    db.commit()
    return {"detail": "Override deleted"}
