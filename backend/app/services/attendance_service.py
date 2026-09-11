import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.enums import AuditAction, TransactionType
from app.models.models import (
    RosterEntry, ShiftMaster, HolidayCalendar, WeeklyOffPattern,
    AttendanceRecord, AttendanceException, AttendanceApprovalRequest, User,
)
from app.services import audit_service, approval_service


def _minutes_between(a: dt.datetime, b: dt.datetime) -> int:
    return int((b - a).total_seconds() // 60)


def generate_roster(db: Session, episode_id: int, start_date: dt.date, end_date: dt.date, weekly_off_weekdays: list[int]) -> list[RosterEntry]:
    """For each date in [start_date, end_date], get-or-create a RosterEntry.
    Idempotent and non-destructive: never overwrites shift_id/is_rest_day
    on an already-existing row."""
    cost_center_id = approval_service.current_cost_center_id(db, episode_id)
    holidays = (
        db.query(HolidayCalendar)
        .filter(HolidayCalendar.date >= start_date, HolidayCalendar.date <= end_date)
        .filter((HolidayCalendar.cost_center_id.is_(None)) | (HolidayCalendar.cost_center_id == cost_center_id))
        .all()
    )
    holiday_dates = {h.date for h in holidays}

    existing = {
        r.date: r
        for r in db.query(RosterEntry).filter(
            RosterEntry.episode_id == episode_id,
            RosterEntry.date >= start_date,
            RosterEntry.date <= end_date,
        ).all()
    }

    entries = []
    current = start_date
    while current <= end_date:
        row = existing.get(current)
        if not row:
            row = RosterEntry(
                episode_id=episode_id,
                date=current,
                is_weekly_off=current.weekday() in weekly_off_weekdays,
                is_holiday=current in holiday_dates,
            )
            db.add(row)
        entries.append(row)
        current += dt.timedelta(days=1)
    return entries


def set_weekly_off_pattern(db: Session, episode_id: int, weekday: int, effective_from: dt.date, user: User) -> WeeklyOffPattern:
    """Mirrors employee_service.add_org_assignment: closes any previously
    open pattern for this episode before inserting the new one."""
    open_pattern = (
        db.query(WeeklyOffPattern)
        .filter(WeeklyOffPattern.episode_id == episode_id, WeeklyOffPattern.effective_to.is_(None))
        .first()
    )
    if open_pattern and open_pattern.effective_from < effective_from:
        open_pattern.effective_to = effective_from - dt.timedelta(days=1)
        db.add(open_pattern)

    pattern = WeeklyOffPattern(episode_id=episode_id, weekday=weekday, effective_from=effective_from)
    db.add(pattern)
    db.flush()
    audit_service.record(db, "WEEKLY_OFF_PATTERN", episode_id, AuditAction.CREATE, user, new_value=f"weekday={weekday}")
    return pattern


def _compute_metrics(shift: ShiftMaster | None, check_in: dt.datetime | None, check_out: dt.datetime | None) -> tuple[int, int, int]:
    """Returns (late_minutes, early_departure_minutes, overtime_minutes)."""
    late_minutes = 0
    early_departure_minutes = 0
    overtime_minutes = 0
    if not shift:
        return late_minutes, early_departure_minutes, overtime_minutes

    if check_in and shift.start_time:
        scheduled_start = dt.datetime.combine(check_in.date(), shift.start_time)
        if check_in > scheduled_start:
            raw_late = _minutes_between(scheduled_start, check_in)
            late_minutes = max(0, raw_late - (shift.grace_minutes or 0))

    if check_out and shift.end_time:
        scheduled_end = dt.datetime.combine(check_out.date(), shift.end_time)
        if check_out < scheduled_end:
            early_departure_minutes = max(0, _minutes_between(check_out, scheduled_end))

    if check_in and check_out and shift.full_day_hours:
        worked_minutes = _minutes_between(check_in, check_out)
        overtime_minutes = max(0, worked_minutes - int(shift.full_day_hours * 60))

    return late_minutes, early_departure_minutes, overtime_minutes


def _raise_exception_if_needed(db: Session, episode_id: int, date_: dt.date, exception_type: str):
    existing = (
        db.query(AttendanceException)
        .filter(
            AttendanceException.episode_id == episode_id,
            AttendanceException.date == date_,
            AttendanceException.exception_type == exception_type,
            AttendanceException.status == "OPEN",
        )
        .first()
    )
    if existing:
        return
    db.add(AttendanceException(episode_id=episode_id, date=date_, exception_type=exception_type))


def mark_attendance(
    db: Session, episode_id: int, date_: dt.date, check_in: dt.datetime | None,
    check_out: dt.datetime | None, shift_id: int | None, status_: str, user: User,
) -> AttendanceRecord:
    record = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.episode_id == episode_id, AttendanceRecord.date == date_)
        .first()
    )
    if not record:
        record = AttendanceRecord(episode_id=episode_id, date=date_)
        db.add(record)

    shift = db.query(ShiftMaster).filter(ShiftMaster.id == shift_id).first() if shift_id else None
    late_minutes, early_departure_minutes, overtime_minutes = _compute_metrics(shift, check_in, check_out)

    record.shift_id = shift_id
    record.check_in = check_in
    record.check_out = check_out
    record.status = status_
    record.late_minutes = late_minutes
    record.early_departure_minutes = early_departure_minutes
    record.overtime_minutes = overtime_minutes
    record.source = "MANUAL"
    db.flush()

    if late_minutes > 0:
        _raise_exception_if_needed(db, episode_id, date_, "LATE")
    if early_departure_minutes > 0:
        _raise_exception_if_needed(db, episode_id, date_, "EARLY_DEPARTURE")

    audit_service.record(db, "ATTENDANCE_RECORD", record.id, AuditAction.UPDATE, user)
    return record


def raise_exception(db: Session, episode_id: int, date_: dt.date, exception_type: str, user: User) -> AttendanceException:
    exc = AttendanceException(episode_id=episode_id, date=date_, exception_type=exception_type)
    db.add(exc)
    db.flush()
    audit_service.record(db, "ATTENDANCE_EXCEPTION", exc.id, AuditAction.CREATE, user, new_value=exception_type)
    return exc


def resolve_exception(db: Session, exception_id: int, resolution_remarks: str | None, user: User) -> AttendanceException:
    exc = db.query(AttendanceException).filter(AttendanceException.id == exception_id).first()
    if not exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attendance exception not found")
    exc.status = "RESOLVED"
    exc.resolution_remarks = resolution_remarks
    db.add(exc)
    audit_service.record(db, "ATTENDANCE_EXCEPTION", exc.id, AuditAction.UPDATE, user, new_value="RESOLVED")
    return exc


def request_attendance_change(
    db: Session, episode_id: int, date_: dt.date, request_type: str,
    requested_check_in: dt.datetime | None, requested_check_out: dt.datetime | None,
    requested_overtime_minutes: int | None, reason: str | None, user: User,
) -> AttendanceApprovalRequest:
    request = AttendanceApprovalRequest(
        episode_id=episode_id, date=date_, request_type=request_type,
        requested_check_in=requested_check_in, requested_check_out=requested_check_out,
        requested_overtime_minutes=requested_overtime_minutes, reason=reason, status="PENDING",
    )
    db.add(request)
    db.flush()
    audit_service.record(db, "ATTENDANCE_APPROVAL_REQUEST", request.id, AuditAction.CREATE, user, new_value=request_type)
    return request


def review_attendance_request(db: Session, request_id: int, user: User, approve: bool, remarks: str | None) -> AttendanceApprovalRequest:
    from app.models.models import EmploymentEpisode  # local import to avoid cycle at module load

    request = db.query(AttendanceApprovalRequest).filter(AttendanceApprovalRequest.id == request_id).first()
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attendance approval request not found")
    if request.status != "PENDING":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This request has already been reviewed")

    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == request.episode_id).first()
    if not episode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee record not found")

    transaction_type = (
        TransactionType.ATTENDANCE_CORRECTION if request.request_type == "CORRECTION" else TransactionType.OVERTIME_APPROVAL
    )
    approval_service.authorize_approval(db, user, episode, transaction_type)

    request.reviewed_by_id = user.id
    request.reviewed_at = dt.datetime.utcnow()
    request.review_remarks = remarks

    if approve:
        record = (
            db.query(AttendanceRecord)
            .filter(AttendanceRecord.episode_id == request.episode_id, AttendanceRecord.date == request.date)
            .first()
        )
        if not record:
            record = AttendanceRecord(episode_id=request.episode_id, date=request.date)
            db.add(record)

        if request.request_type == "CORRECTION":
            shift = db.query(ShiftMaster).filter(ShiftMaster.id == record.shift_id).first() if record.shift_id else None
            record.check_in = request.requested_check_in
            record.check_out = request.requested_check_out
            late_minutes, early_departure_minutes, overtime_minutes = _compute_metrics(shift, record.check_in, record.check_out)
            record.late_minutes = late_minutes
            record.early_departure_minutes = early_departure_minutes
            record.overtime_minutes = overtime_minutes
            record.source = "CORRECTION"
        else:  # OVERTIME
            record.overtime_minutes = request.requested_overtime_minutes or 0
            record.source = "CORRECTION"
        db.add(record)
        request.status = "APPROVED"
        audit_service.record(db, "ATTENDANCE_APPROVAL_REQUEST", request.id, AuditAction.APPROVE, user)
    else:
        request.status = "REJECTED"
        audit_service.record(db, "ATTENDANCE_APPROVAL_REQUEST", request.id, AuditAction.REJECT, user, new_value=remarks)

    db.add(request)
    return request
