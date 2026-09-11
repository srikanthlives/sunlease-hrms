import calendar
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.enums import Permission, RoleName
from app.models.models import (
    EmploymentEpisode, RosterEntry, AttendanceRecord, AttendanceException,
    AttendanceApprovalRequest, ShiftMaster, User,
)
from app.schemas.attendance import (
    ShiftMasterIn, RosterGenerateIn, WeeklyOffPatternIn, RosterEntryUpdate, AttendanceRecordIn,
    ExceptionResolveIn, AttendanceRequestIn, AttendanceRequestReview, AttendanceBulkSaveIn,
)
from app.services import (
    audit_service, attendance_service, approval_service, employee_service, permission_service,
    attendance_bulk_import_service,
)

router = APIRouter(prefix="/api/v1/attendance", tags=["attendance"], dependencies=[Depends(get_current_user)])


def _shift_dict(s: ShiftMaster) -> dict:
    return {
        "id": s.id, "code": s.code, "name": s.name, "start_time": s.start_time, "end_time": s.end_time,
        "break_minutes": s.break_minutes, "grace_minutes": s.grace_minutes,
        "half_day_hours": s.half_day_hours, "full_day_hours": s.full_day_hours,
        "is_night_shift": s.is_night_shift, "is_active": s.is_active,
    }


@router.get("/shifts")
def list_shifts(db: Session = Depends(get_db)):
    rows = db.query(ShiftMaster).filter(ShiftMaster.is_active.is_(True)).order_by(ShiftMaster.name).all()
    return [_shift_dict(s) for s in rows]


@router.post("/shifts", dependencies=[Depends(require_permission(Permission.ROSTER_MANAGE))])
def create_shift(payload: ShiftMasterIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.query(ShiftMaster).filter(ShiftMaster.code == payload.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Shift code already exists")
    obj = ShiftMaster(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit_service.record(db, "SHIFT_MASTER", obj.id, "CREATE", user)
    db.commit()
    db.refresh(obj)
    return _shift_dict(obj)


@router.put("/shifts/{shift_id}", dependencies=[Depends(require_permission(Permission.ROSTER_MANAGE))])
def update_shift(shift_id: int, payload: ShiftMasterIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.query(ShiftMaster).filter(ShiftMaster.id == shift_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shift not found")
    dupe = db.query(ShiftMaster).filter(ShiftMaster.code == payload.code, ShiftMaster.id != shift_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Shift code already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    audit_service.record(db, "SHIFT_MASTER", obj.id, "UPDATE", user)
    db.commit()
    db.refresh(obj)
    return _shift_dict(obj)


def _get_episode(db: Session, episode_id: int) -> EmploymentEpisode:
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == episode_id).first()
    if not episode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee record not found")
    return episode


def _check_scope(db: Session, user: User, episode: EmploymentEpisode):
    cc_id = approval_service.current_cost_center_id(db, episode.id)
    if not permission_service.can_see_cost_center(db, user, cc_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This employee is outside your Cost Center scope")


def _roster_dict(r: RosterEntry) -> dict:
    return {
        "id": r.id, "episode_id": r.episode_id, "date": r.date,
        "shift_id": r.shift_id, "second_shift_id": r.second_shift_id,
        "is_weekly_off": r.is_weekly_off, "is_rest_day": r.is_rest_day, "is_holiday": r.is_holiday,
        "remarks": r.remarks,
    }


def _record_dict(r: AttendanceRecord) -> dict:
    return {
        "id": r.id, "episode_id": r.episode_id, "date": r.date, "shift_id": r.shift_id,
        "check_in": r.check_in, "check_out": r.check_out, "status": r.status,
        "late_minutes": r.late_minutes, "early_departure_minutes": r.early_departure_minutes,
        "overtime_minutes": r.overtime_minutes, "source": r.source, "remarks": r.remarks,
    }


def _exception_dict(e: AttendanceException) -> dict:
    return {
        "id": e.id, "episode_id": e.episode_id, "date": e.date, "exception_type": e.exception_type,
        "status": e.status, "resolution_remarks": e.resolution_remarks,
    }


def _request_dict(r: AttendanceApprovalRequest) -> dict:
    return {
        "id": r.id, "episode_id": r.episode_id, "date": r.date, "request_type": r.request_type,
        "requested_check_in": r.requested_check_in, "requested_check_out": r.requested_check_out,
        "requested_overtime_minutes": r.requested_overtime_minutes, "reason": r.reason,
        "status": r.status, "reviewed_by": r.reviewed_by.username if r.reviewed_by else None,
        "reviewed_at": r.reviewed_at, "review_remarks": r.review_remarks, "created_at": r.created_at,
    }


@router.post("/roster/generate", dependencies=[Depends(require_permission(Permission.ROSTER_MANAGE))])
def generate_roster(payload: RosterGenerateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, payload.episode_id)
    _check_scope(db, user, episode)
    entries = attendance_service.generate_roster(db, episode.id, payload.start_date, payload.end_date, payload.weekly_off_weekdays)
    audit_service.record(db, "ROSTER", episode.id, "UPDATE", user, new_value=f"{payload.start_date}..{payload.end_date}")
    db.commit()
    return {"ok": True, "count": len(entries)}


@router.post("/weekly-off-pattern", dependencies=[Depends(require_permission(Permission.ROSTER_MANAGE))])
def set_weekly_off_pattern(payload: WeeklyOffPatternIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, payload.episode_id)
    _check_scope(db, user, episode)
    attendance_service.set_weekly_off_pattern(db, episode.id, payload.weekday, payload.effective_from, user)
    db.commit()
    return {"ok": True}


@router.get("/roster/{episode_id}", dependencies=[Depends(require_permission(Permission.ATTENDANCE_VIEW))])
def get_roster(episode_id: int, start_date: date, end_date: date, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    rows = (
        db.query(RosterEntry)
        .filter(RosterEntry.episode_id == episode_id, RosterEntry.date >= start_date, RosterEntry.date <= end_date)
        .order_by(RosterEntry.date)
        .all()
    )
    return [_roster_dict(r) for r in rows]


@router.patch("/roster/{episode_id}/{entry_date}", dependencies=[Depends(require_permission(Permission.ROSTER_MANAGE))])
def update_roster_entry(episode_id: int, entry_date: date, payload: RosterEntryUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    row = db.query(RosterEntry).filter(RosterEntry.episode_id == episode_id, RosterEntry.date == entry_date).first()
    if not row:
        row = RosterEntry(episode_id=episode_id, date=entry_date)
        db.add(row)
    row.shift_id = payload.shift_id
    row.second_shift_id = payload.second_shift_id
    row.is_rest_day = payload.is_rest_day
    row.remarks = payload.remarks
    audit_service.record(db, "ROSTER_ENTRY", episode_id, "UPDATE", user, new_value=str(entry_date))
    db.commit()
    return {"ok": True}


@router.get("/records", dependencies=[Depends(require_permission(Permission.ATTENDANCE_VIEW))])
def list_records_aggregate(
    cost_center_id: int | None = Query(None),
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Aggregate view for a whole Cost Center's month (the Phase A/C global
    filter): for every episode with an OrgAssignment overlapping that month
    (optionally restricted to cost_center_id), returns its AttendanceRecord
    rows for the month. Days with no AttendanceRecord yet still get a
    placeholder entry (id=None, status=None) so a later grid can render one
    cell per calendar day without special-casing missing rows."""
    _, last_day = calendar.monthrange(year, month)
    month_start, month_end = date(year, month, 1), date(year, month, last_day)
    episodes = employee_service.episodes_in_cost_center_during(db, cost_center_id, month_start, month_end)
    episodes = [e for e in episodes if permission_service.can_see_cost_center(db, user, approval_service.current_cost_center_id(db, e.id))]
    episode_ids = [e.id for e in episodes]

    records_by_episode = {}
    if episode_ids:
        rows = (
            db.query(AttendanceRecord)
            .filter(AttendanceRecord.episode_id.in_(episode_ids), AttendanceRecord.date >= month_start, AttendanceRecord.date <= month_end)
            .all()
        )
        for r in rows:
            records_by_episode.setdefault(r.episode_id, {})[r.date] = r

    result = []
    for e in episodes:
        by_date = records_by_episode.get(e.id, {})
        day_records = []
        d = month_start
        while d <= month_end:
            record = by_date.get(d)
            day_records.append(_record_dict(record) if record else {
                "id": None, "episode_id": e.id, "date": d, "shift_id": None,
                "check_in": None, "check_out": None, "status": None,
                "late_minutes": 0, "early_departure_minutes": 0, "overtime_minutes": 0,
                "source": None, "remarks": None,
            })
            d += timedelta(days=1)
        result.append({
            "episode_id": e.id,
            "employee_number": e.employee_number,
            "first_name": e.employee.first_name,
            "last_name": e.employee.last_name,
            "records": day_records,
        })
    return result


@router.get("/bulk-upload-template", dependencies=[Depends(require_permission(Permission.ATTENDANCE_MARK))])
def download_bulk_upload_template(
    cost_center_id: int | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Downloadable .xlsx: header row + one row per active employee per
    calendar day of the given month (if cost_center_id/year/month all
    given), else header + one sample row - see
    services/attendance_bulk_import_service.py."""
    wb = attendance_bulk_import_service.build_attendance_template_workbook(db, cost_center_id, year, month)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=hrms_attendance_bulk_upload_template.xlsx"},
    )


@router.post("/bulk-upload", dependencies=[Depends(require_permission(Permission.ATTENDANCE_MARK))])
def bulk_upload_attendance(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Each row upserts through attendance_service.mark_attendance (same
    late/early/overtime computation as manual single-record entry), inside
    a per-row savepoint so one bad row doesn't abort the whole batch."""
    content = file.file.read()
    result = attendance_bulk_import_service.import_attendance_workbook(db, content, user)
    db.commit()
    return result


@router.post("/records/bulk", dependencies=[Depends(require_permission(Permission.ATTENDANCE_MARK))])
def mark_attendance_bulk(payload: AttendanceBulkSaveIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Applies a batch of grid edits in one transaction - collects
    per-item errors (bad episode_id, out-of-scope Cost Center) and applies
    the rest, matching the bulk-import UX, then commits once."""
    updated = 0
    errors = []
    for idx, item in enumerate(payload.items):
        try:
            episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == item.episode_id).first()
            if not episode:
                raise ValueError(f"Employee record {item.episode_id} not found")
            _check_scope(db, user, episode)
            attendance_service.mark_attendance(
                db, episode.id, item.date, item.check_in, item.check_out, item.shift_id, item.status, user,
            )
            updated += 1
        except HTTPException as exc:
            errors.append({"index": idx, "episode_id": item.episode_id, "date": str(item.date), "message": exc.detail})
        except ValueError as exc:
            errors.append({"index": idx, "episode_id": item.episode_id, "date": str(item.date), "message": str(exc)})
    db.commit()
    return {"updated": updated, "errors": errors}


@router.get("/records/{episode_id}", dependencies=[Depends(require_permission(Permission.ATTENDANCE_VIEW))])
def list_records(episode_id: int, start_date: date, end_date: date, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    rows = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.episode_id == episode_id, AttendanceRecord.date >= start_date, AttendanceRecord.date <= end_date)
        .order_by(AttendanceRecord.date)
        .all()
    )
    return [_record_dict(r) for r in rows]


@router.post("/records", dependencies=[Depends(require_permission(Permission.ATTENDANCE_MARK))])
def mark_attendance(payload: AttendanceRecordIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, payload.episode_id)
    _check_scope(db, user, episode)
    record = attendance_service.mark_attendance(
        db, episode.id, payload.date, payload.check_in, payload.check_out, payload.shift_id, payload.status, user,
    )
    db.commit()
    return {"ok": True, "id": record.id}


@router.get("/exceptions/{episode_id}", dependencies=[Depends(require_permission(Permission.ATTENDANCE_VIEW))])
def list_exceptions(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    rows = db.query(AttendanceException).filter(AttendanceException.episode_id == episode_id).order_by(AttendanceException.date.desc()).all()
    return [_exception_dict(e) for e in rows]


@router.post("/exceptions/{exception_id}/resolve", dependencies=[Depends(require_permission(Permission.ATTENDANCE_APPROVE))])
def resolve_exception(exception_id: int, payload: ExceptionResolveIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attendance_service.resolve_exception(db, exception_id, payload.resolution_remarks, user)
    db.commit()
    return {"ok": True}


@router.post("/requests", dependencies=[Depends(require_permission(Permission.ATTENDANCE_CORRECT))])
def create_attendance_request(payload: AttendanceRequestIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, payload.episode_id)
    _check_scope(db, user, episode)
    request = attendance_service.request_attendance_change(
        db, episode.id, payload.date, payload.request_type, payload.requested_check_in,
        payload.requested_check_out, payload.requested_overtime_minutes, payload.reason, user,
    )
    db.commit()
    return {"ok": True, "id": request.id}


@router.get("/requests", dependencies=[Depends(require_permission(Permission.ATTENDANCE_VIEW))])
def list_requests(status_: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(AttendanceApprovalRequest)
    if status_:
        query = query.filter(AttendanceApprovalRequest.status == status_)
    rows = query.order_by(AttendanceApprovalRequest.created_at.desc()).all()

    result = []
    for r in rows:
        episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == r.episode_id).first()
        cc_id = approval_service.current_cost_center_id(db, r.episode_id) if episode else None
        if not permission_service.can_see_cost_center(db, user, cc_id):
            continue
        result.append(_request_dict(r))
    return result


@router.post("/requests/{request_id}/approve", dependencies=[Depends(require_permission(Permission.ATTENDANCE_APPROVE))])
def approve_request(request_id: int, payload: AttendanceRequestReview, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attendance_service.review_attendance_request(db, request_id, user, approve=True, remarks=payload.remarks)
    db.commit()
    return {"ok": True}


@router.post("/requests/{request_id}/reject", dependencies=[Depends(require_permission(Permission.ATTENDANCE_APPROVE))])
def reject_request(request_id: int, payload: AttendanceRequestReview, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attendance_service.review_attendance_request(db, request_id, user, approve=False, remarks=payload.remarks)
    db.commit()
    return {"ok": True}
