from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_payroll_or_admin, require_any

router = APIRouter(prefix="/adhoc-entries", tags=["adhoc-entries"])


@router.get("", response_model=list[schemas.AdhocEntryOut])
def list_adhoc(month: int, year: int, employee_id: int | None = None, db: Session = Depends(get_db), _=Depends(require_any)):
    q = db.query(models.AdhocEntry).filter_by(month=month, year=year)
    if employee_id:
        q = q.filter_by(employee_id=employee_id)
    return q.all()


@router.post("", response_model=schemas.AdhocEntryOut)
def create_adhoc(payload: schemas.AdhocEntryIn, db: Session = Depends(get_db), current_user: models.User = Depends(require_payroll_or_admin)):
    emp = db.query(models.Employee).get(payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    entry = models.AdhocEntry(**payload.model_dump(), created_by=current_user.username)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def delete_adhoc(entry_id: int, db: Session = Depends(get_db), _=Depends(require_payroll_or_admin)):
    entry = db.query(models.AdhocEntry).get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"detail": "Deleted"}
