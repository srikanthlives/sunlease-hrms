from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_payroll_or_admin, require_any
from ..utils.excel import parse_attendance_upload, parse_daily_attendance_day_upload, parse_daily_attendance_wide_upload
from ..utils.eligibility import is_eligible_for_period, is_eligible_on_date
from ..utils.attendance_calc import compute_monthly_attendance_stats, compute_el_balance, days_in_month, check_el_available

router = APIRouter(prefix="/attendance", tags=["attendance"])

_VALID_STATUSES = {s.value for s in models.AttendanceStatus}


@router.get("", response_model=list[schemas.AttendanceOut])
def list_attendance(month: int, year: int, db: Session = Depends(get_db), _=Depends(require_any)):
    return db.query(models.Attendance).filter_by(month=month, year=year).all()


@router.post("", response_model=schemas.AttendanceOut)
def upsert_attendance(payload: schemas.AttendanceIn, db: Session = Depends(get_db), _=Depends(require_payroll_or_admin)):
    record = db.query(models.Attendance).filter_by(
        employee_id=payload.employee_id, month=payload.month, year=payload.year
    ).first()
    if record:
        for k, v in payload.model_dump().items():
            setattr(record, k, v)
    else:
        record = models.Attendance(**payload.model_dump())
        db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post("/upload", response_model=schemas.BulkUploadResult)
async def upload_attendance(month: int, year: int, file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(require_payroll_or_admin)):
    content = await file.read()
    try:
        rows = parse_attendance_upload(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    inserted, updated, errors = 0, 0, []
    for row in rows:
        emp = db.query(models.Employee).filter_by(employee_code=row["employee_code"]).first()
        if not emp:
            errors.append(f"Unknown employee_code '{row['employee_code']}'")
            continue
        record = db.query(models.Attendance).filter_by(employee_id=emp.id, month=month, year=year).first()
        if record:
            record.total_days = row["total_days"]
            record.present_days = row["present_days"]
            record.paid_leave_days = row["paid_leave_days"]
            record.lop_days = row["lop_days"]
            record.remarks = row["remarks"]
            updated += 1
        else:
            db.add(models.Attendance(
                employee_id=emp.id, month=month, year=year,
                total_days=row["total_days"], present_days=row["present_days"],
                paid_leave_days=row["paid_leave_days"], lop_days=row["lop_days"], remarks=row["remarks"],
            ))
            inserted += 1
    db.commit()
    return schemas.BulkUploadResult(inserted=inserted, updated=updated, errors=errors)


# ================= Day-by-day attendance management =================

@router.get("/grid", response_model=schemas.AttendanceGridOut)
def attendance_grid(month: int, year: int, db: Session = Depends(get_db), _=Depends(require_payroll_or_admin)):
    """
    The full monthly attendance grid: every day of the month x every employee ELIGIBLE for
    this period (joined by now, not yet left before it - same rule payroll uses), with their
    per-day status and a computed monthly summary.
    """
    employees = [e for e in db.query(models.Employee).all() if is_eligible_for_period(e, month, year)]
    n_days = days_in_month(year, month)
    prefix = f"{year:04d}-{month:02d}-"

    rows = []
    for emp in employees:
        records = (
            db.query(models.DailyAttendance)
            .filter(models.DailyAttendance.employee_id == emp.id)
            .filter(models.DailyAttendance.date.like(f"{prefix}%"))
            .all()
        )
        statuses = {r.date: r.status.value for r in records}
        stats = compute_monthly_attendance_stats(db, emp.id, month, year) or {
            "total_days": float(n_days), "present_days": 0.0, "lop_days": 0.0,
            "paid_leave_days": 0.0, "marked_days": 0,
            "total": 0.0, "present": 0.0, "week_offs": 0.0, "rest_days": 0.0,
            "absent": 0.0, "el": 0.0, "suspended": 0.0, "lop": 0.0,
        }
        rows.append(schemas.AttendanceGridRow(
            employee_id=emp.id, employee_code=emp.employee_code,
            name=f"{emp.first_name} {emp.last_name}".strip(),
            statuses=statuses, **stats,
        ))

    return schemas.AttendanceGridOut(month=month, year=year, days=list(range(1, n_days + 1)), rows=rows)


@router.post("/daily", response_model=schemas.DailyAttendanceOut)
def upsert_daily_attendance(payload: schemas.DailyAttendanceIn, db: Session = Depends(get_db), current_user: models.User = Depends(require_payroll_or_admin)):
    emp = db.query(models.Employee).get(payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if not is_eligible_on_date(emp, payload.date):
        raise HTTPException(status_code=400, detail="Attendance cannot be marked outside the employee's joining or leaving window")

    if payload.status == models.AttendanceStatus.EARNED_LEAVE:
        error = check_el_available(db, payload.employee_id, payload.date)
        if error:
            raise HTTPException(status_code=400, detail=error)

    record = db.query(models.DailyAttendance).filter_by(employee_id=payload.employee_id, date=payload.date).first()
    if record:
        record.status = payload.status
        record.remarks = payload.remarks
        record.uploaded_by = current_user.username
    else:
        record = models.DailyAttendance(
            employee_id=payload.employee_id, date=payload.date, status=payload.status,
            remarks=payload.remarks, uploaded_by=current_user.username,
        )
        db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/daily")
def delete_daily_attendance(employee_id: int, date: str, db: Session = Depends(get_db), _=Depends(require_payroll_or_admin)):
    record = db.query(models.DailyAttendance).filter_by(employee_id=employee_id, date=date).first()
    if not record:
        raise HTTPException(status_code=404, detail="No attendance record for that employee/date")
    db.delete(record)
    db.commit()
    return {"detail": "Cleared"}


@router.post("/daily/upload-day", response_model=schemas.BulkUploadResult)
async def upload_daily_attendance_for_day(
    date: str, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.User = Depends(require_payroll_or_admin),
):
    """Bulk-mark a single day for many employees. Columns: employee_code, status, remarks (optional)."""
    content = await file.read()
    try:
        rows = parse_daily_attendance_day_upload(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    inserted, updated, errors = 0, 0, []
    for row in rows:
        if row["status"] not in _VALID_STATUSES:
            errors.append(f"{row['employee_code']}: invalid status '{row['status']}' (expected one of {sorted(_VALID_STATUSES)})")
            continue
        emp = db.query(models.Employee).filter_by(employee_code=row["employee_code"]).first()
        if not emp:
            errors.append(f"Unknown employee_code '{row['employee_code']}'")
            continue
        if not is_eligible_on_date(emp, date):
            errors.append(f"{row['employee_code']}: attendance cannot be uploaded outside the employee's joining or leaving window")
            continue
        if row["status"] == models.AttendanceStatus.EARNED_LEAVE.value:
            el_error = check_el_available(db, emp.id, date)
            if el_error:
                errors.append(f"{row['employee_code']}: {el_error}")
                continue
        record = db.query(models.DailyAttendance).filter_by(employee_id=emp.id, date=date).first()
        if record:
            record.status = row["status"]
            record.remarks = row["remarks"]
            record.uploaded_by = current_user.username
            updated += 1
        else:
            db.add(models.DailyAttendance(
                employee_id=emp.id, date=date, status=row["status"],
                remarks=row["remarks"], uploaded_by=current_user.username,
            ))
            inserted += 1
    db.commit()
    return schemas.BulkUploadResult(inserted=inserted, updated=updated, errors=errors)


@router.post("/daily/upload-month", response_model=schemas.BulkUploadResult)
async def upload_daily_attendance_for_month(
    month: int, year: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.User = Depends(require_payroll_or_admin),
):
    """
    Bulk-mark a whole month at once, WIDE format: one row per employee. Columns: employee_code,
    employee_name (optional, informational only), then one column per day of the month
    (1, 2, 3, ... up to 28/30/31), each holding that day's status code.
    """
    content = await file.read()
    try:
        rows = parse_daily_attendance_wide_upload(content, year, month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    inserted, updated, errors = 0, 0, []
    for row in sorted(rows, key=lambda r: r["date"]):  # chronological, so EL balance checks see earlier-in-file work days
        if row["status"] not in _VALID_STATUSES:
            errors.append(f"{row['employee_code']} {row['date']}: invalid status '{row['status']}' (expected one of {sorted(_VALID_STATUSES)})")
            continue
        emp = db.query(models.Employee).filter_by(employee_code=row["employee_code"]).first()
        if not emp:
            errors.append(f"Unknown employee_code '{row['employee_code']}'")
            continue
        if not is_eligible_on_date(emp, row["date"]):
            errors.append(f"{row['employee_code']} {row['date']}: attendance cannot be uploaded outside the employee's joining or leaving window")
            continue
        if row["status"] == models.AttendanceStatus.EARNED_LEAVE.value:
            el_error = check_el_available(db, emp.id, row["date"])
            if el_error:
                errors.append(f"{row['employee_code']} {row['date']}: {el_error}")
                continue
        record = db.query(models.DailyAttendance).filter_by(employee_id=emp.id, date=row["date"]).first()
        if record:
            record.status = row["status"]
            record.remarks = row["remarks"]
            record.uploaded_by = current_user.username
            updated += 1
        else:
            db.add(models.DailyAttendance(
                employee_id=emp.id, date=row["date"], status=row["status"],
                remarks=row["remarks"], uploaded_by=current_user.username,
            ))
            inserted += 1
    db.commit()
    return schemas.BulkUploadResult(inserted=inserted, updated=updated, errors=errors)


@router.get("/el-balance", response_model=list[schemas.ELBalanceOut])
def el_balance(year: int, upto_month: int = 12, employee_id: int | None = None, db: Session = Depends(get_db), current_user: models.User = Depends(require_any)):
    """Earned-leave accrual/balance for the given calendar year (up to upto_month, default December)."""
    if current_user.role == models.UserRole.EMPLOYEE:
        employees = [db.query(models.Employee).get(current_user.employee_id)]
    elif employee_id:
        emp = db.query(models.Employee).get(employee_id)
        employees = [emp] if emp else []
    else:
        employees = db.query(models.Employee).all()

    results = []
    for emp in employees:
        if not emp:
            continue
        balance = compute_el_balance(db, emp.id, year, upto_month)
        results.append(schemas.ELBalanceOut(
            employee_id=emp.id, employee_code=emp.employee_code,
            name=f"{emp.first_name} {emp.last_name}".strip(), **balance,
        ))
    return results
