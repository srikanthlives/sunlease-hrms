from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_payroll_or_admin, require_any
from ..utils.excel import parse_payments_upload

router = APIRouter(prefix="/payments", tags=["salary-payments"])


@router.get("", response_model=list[schemas.SalaryPaymentOut])
def list_payments(month: int, year: int, employee_id: int | None = None, db: Session = Depends(get_db), current_user: models.User = Depends(require_any)):
    q = db.query(models.SalaryPayment).filter_by(month=month, year=year)
    if current_user.role == models.UserRole.EMPLOYEE:
        q = q.filter_by(employee_id=current_user.employee_id)
    elif employee_id:
        q = q.filter_by(employee_id=employee_id)
    return q.order_by(models.SalaryPayment.created_at).all()


@router.post("", response_model=schemas.SalaryPaymentOut)
def create_payment(payload: schemas.SalaryPaymentIn, db: Session = Depends(get_db), current_user: models.User = Depends(require_payroll_or_admin)):
    emp = db.query(models.Employee).get(payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    payment = models.SalaryPayment(**payload.model_dump(), uploaded_by=current_user.username)
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


@router.post("/upload", response_model=schemas.BulkUploadResult)
async def upload_payments(
    month: int, year: int, file: UploadFile = File(...),
    db: Session = Depends(get_db), current_user: models.User = Depends(require_payroll_or_admin),
):
    """
    Bulk-upload part-payments made towards a month's salary. Columns: employee_code, amount,
    transaction_id (optional), payment_date (optional), remarks (optional). Multiple rows for
    the same employee/month are all kept (e.g. an advance + a balance payment) - they are not
    merged or overwritten, so re-uploading the same file will create duplicate entries.
    """
    content = await file.read()
    try:
        rows = parse_payments_upload(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    inserted, errors = 0, []
    for row in rows:
        emp = db.query(models.Employee).filter_by(employee_code=row["employee_code"]).first()
        if not emp:
            errors.append(f"Unknown employee_code '{row['employee_code']}'")
            continue
        db.add(models.SalaryPayment(
            employee_id=emp.id, month=month, year=year, amount=row["amount"],
            transaction_id=row["transaction_id"], payment_date=row["payment_date"],
            remarks=row["remarks"], uploaded_by=current_user.username,
        ))
        inserted += 1

    db.commit()
    return schemas.BulkUploadResult(inserted=inserted, updated=0, errors=errors)


@router.delete("/{payment_id}")
def delete_payment(payment_id: int, db: Session = Depends(get_db), _=Depends(require_payroll_or_admin)):
    payment = db.query(models.SalaryPayment).get(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    db.delete(payment)
    db.commit()
    return {"detail": "Payment deleted"}
