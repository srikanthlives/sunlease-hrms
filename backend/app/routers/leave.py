import calendar
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.enums import Permission
from app.models.models import (
    EmploymentEpisode, LeaveType, LeaveEligibilityRule, HolidayCalendar, LeaveApplication, User,
)
from app.schemas.leave import (
    LeaveTypeIn, LeaveEligibilityRuleIn, HolidayCalendarIn, LeaveApplicationIn, LeaveApplicationReview,
)
from app.services import audit_service, employee_service, leave_service, approval_service, permission_service

router = APIRouter(prefix="/api/v1/leave", tags=["leave"], dependencies=[Depends(get_current_user)])


def _get_episode(db: Session, episode_id: int) -> EmploymentEpisode:
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == episode_id).first()
    if not episode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee record not found")
    return episode


def _check_scope(db: Session, user: User, episode: EmploymentEpisode):
    cc_id = approval_service.current_cost_center_id(db, episode.id)
    if not permission_service.can_see_cost_center(db, user, cc_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This employee is outside your Cost Center scope")


def _leave_type_dict(t: LeaveType) -> dict:
    return {
        "id": t.id, "code": t.code, "name": t.name, "is_paid": t.is_paid,
        "accrual_frequency": t.accrual_frequency, "accrual_amount": t.accrual_amount,
        "max_balance": t.max_balance, "carry_forward_limit": t.carry_forward_limit,
        "requires_approval": t.requires_approval, "is_active": t.is_active,
    }


def _eligibility_rule_dict(r: LeaveEligibilityRule) -> dict:
    return {
        "id": r.id, "leave_type_id": r.leave_type_id, "employee_category_id": r.employee_category_id,
        "cost_center_id": r.cost_center_id, "min_service_months": r.min_service_months,
        "annual_entitlement": r.annual_entitlement,
    }


def _holiday_dict(h: HolidayCalendar) -> dict:
    return {"id": h.id, "name": h.name, "date": h.date, "cost_center_id": h.cost_center_id, "is_optional": h.is_optional}


def _application_dict(a: LeaveApplication) -> dict:
    return {
        "id": a.id, "episode_id": a.episode_id, "leave_type_id": a.leave_type_id,
        "start_date": a.start_date, "end_date": a.end_date, "is_half_day": a.is_half_day,
        "half_day_session": a.half_day_session, "days": a.days, "reason": a.reason,
        "status": a.status, "reviewed_by": a.reviewed_by.username if a.reviewed_by else None,
        "reviewed_at": a.reviewed_at, "review_remarks": a.review_remarks, "created_at": a.created_at,
        "attachment_file_name": a.attachment_file_name,
    }


# ---------------------------------------------------------------------------
# Master data: Leave Types / Eligibility Rules / Holiday Calendar
# ---------------------------------------------------------------------------

@router.get("/types")
def list_leave_types(db: Session = Depends(get_db)):
    rows = db.query(LeaveType).filter(LeaveType.is_active.is_(True)).order_by(LeaveType.name).all()
    return [_leave_type_dict(t) for t in rows]


@router.post("/types", dependencies=[Depends(require_permission(Permission.LEAVE_ADMIN))])
def create_leave_type(payload: LeaveTypeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.query(LeaveType).filter(LeaveType.code == payload.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Leave Type code already exists")
    obj = LeaveType(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit_service.record(db, "LEAVE_TYPE", obj.id, "CREATE", user)
    db.commit()
    db.refresh(obj)
    return _leave_type_dict(obj)


@router.put("/types/{type_id}", dependencies=[Depends(require_permission(Permission.LEAVE_ADMIN))])
def update_leave_type(type_id: int, payload: LeaveTypeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.query(LeaveType).filter(LeaveType.id == type_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave Type not found")
    dupe = db.query(LeaveType).filter(LeaveType.code == payload.code, LeaveType.id != type_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Leave Type code already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    audit_service.record(db, "LEAVE_TYPE", obj.id, "UPDATE", user)
    db.commit()
    db.refresh(obj)
    return _leave_type_dict(obj)


@router.get("/eligibility-rules")
def list_eligibility_rules(db: Session = Depends(get_db)):
    rows = db.query(LeaveEligibilityRule).all()
    return [_eligibility_rule_dict(r) for r in rows]


@router.post("/eligibility-rules", dependencies=[Depends(require_permission(Permission.LEAVE_ADMIN))])
def create_eligibility_rule(payload: LeaveEligibilityRuleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = LeaveEligibilityRule(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit_service.record(db, "LEAVE_ELIGIBILITY_RULE", obj.id, "CREATE", user)
    db.commit()
    db.refresh(obj)
    return _eligibility_rule_dict(obj)


@router.get("/holiday-calendar")
def list_holidays(cost_center_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(HolidayCalendar)
    if cost_center_id is not None:
        query = query.filter((HolidayCalendar.cost_center_id.is_(None)) | (HolidayCalendar.cost_center_id == cost_center_id))
    rows = query.order_by(HolidayCalendar.date).all()
    return [_holiday_dict(h) for h in rows]


@router.post("/holiday-calendar", dependencies=[Depends(require_permission(Permission.LEAVE_ADMIN))])
def create_holiday(payload: HolidayCalendarIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = HolidayCalendar(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit_service.record(db, "HOLIDAY_CALENDAR", obj.id, "CREATE", user)
    db.commit()
    db.refresh(obj)
    return _holiday_dict(obj)


# ---------------------------------------------------------------------------
# Balances / Applications / History
# ---------------------------------------------------------------------------

@router.get("/balances/{episode_id}", dependencies=[Depends(require_permission(Permission.ATTENDANCE_VIEW))])
def get_balances(episode_id: int, year: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    year = year or date.today().year
    leave_types = db.query(LeaveType).filter(LeaveType.is_active.is_(True)).all()
    balances = []
    for lt in leave_types:
        balance = leave_service.get_or_create_balance(db, episode_id, lt.id, year)
        d = leave_service.balance_dict(balance)
        d["leave_type_code"] = lt.code
        d["leave_type_name"] = lt.name
        balances.append(d)
    db.commit()
    return balances


@router.post("/applications", dependencies=[Depends(require_permission(Permission.LEAVE_APPLY))])
def apply_leave(payload: LeaveApplicationIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, payload.episode_id)
    _check_scope(db, user, episode)
    application = leave_service.apply_leave(
        db, episode.id, payload.leave_type_id, payload.start_date, payload.end_date,
        payload.is_half_day, payload.half_day_session, payload.reason, user,
    )
    db.commit()
    return {"ok": True, "id": application.id, "status": application.status, "days": application.days}


@router.get("/applications", dependencies=[Depends(require_permission(Permission.ATTENDANCE_VIEW))])
def list_applications(
    episode_id: int | None = None,
    status_: str | None = None,
    cost_center_id: int | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(LeaveApplication)
    if episode_id is not None:
        query = query.filter(LeaveApplication.episode_id == episode_id)
    if status_:
        query = query.filter(LeaveApplication.status == status_)

    # year+month (+ optional cost_center_id): restrict to episodes that were
    # in that cost center during the month, and applications whose date
    # range overlaps the month - same overlap-helper pattern as employees/attendance.
    if year is not None and month is not None:
        _, last_day = calendar.monthrange(year, month)
        month_start, month_end = date(year, month, 1), date(year, month, last_day)
        allowed_episode_ids = {
            ep.id for ep in employee_service.episodes_in_cost_center_during(db, cost_center_id, month_start, month_end)
        }
        if not allowed_episode_ids:
            return []
        query = query.filter(
            LeaveApplication.episode_id.in_(allowed_episode_ids),
            LeaveApplication.start_date <= month_end,
            LeaveApplication.end_date >= month_start,
        )

    rows = query.order_by(LeaveApplication.created_at.desc()).all()

    result = []
    for a in rows:
        cc_id = approval_service.current_cost_center_id(db, a.episode_id)
        if not permission_service.can_see_cost_center(db, user, cc_id):
            continue
        result.append(_application_dict(a))
    return result


@router.post("/applications/{application_id}/approve", dependencies=[Depends(require_permission(Permission.LEAVE_APPROVE))])
def approve_application(application_id: int, payload: LeaveApplicationReview, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    leave_service.review_leave_application(db, application_id, user, approve=True, remarks=payload.remarks)
    db.commit()
    return {"ok": True}


@router.post("/applications/{application_id}/reject", dependencies=[Depends(require_permission(Permission.LEAVE_APPROVE))])
def reject_application(application_id: int, payload: LeaveApplicationReview, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    leave_service.review_leave_application(db, application_id, user, approve=False, remarks=payload.remarks)
    db.commit()
    return {"ok": True}


@router.post("/applications/{application_id}/cancel", dependencies=[Depends(require_permission(Permission.LEAVE_APPLY))])
def cancel_application(application_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    leave_service.cancel_leave(db, application_id, user)
    db.commit()
    return {"ok": True}


def _get_application(db: Session, application_id: int) -> LeaveApplication:
    application = db.query(LeaveApplication).filter(LeaveApplication.id == application_id).first()
    if not application:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave application not found")
    return application


@router.post("/applications/{application_id}/attachment", dependencies=[Depends(require_permission(Permission.LEAVE_APPLY))])
def upload_application_attachment(
    application_id: int, file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Supporting document for a leave application (e.g. a medical
    certificate for Sick Leave) - one file per application, replacing any
    prior upload."""
    application = _get_application(db, application_id)
    episode = _get_episode(db, application.episode_id)
    _check_scope(db, user, episode)
    leave_service.save_attachment(db, application, file, user)
    db.commit()
    return {"ok": True, "attachment_file_name": application.attachment_file_name}


@router.get("/applications/{application_id}/attachment", dependencies=[Depends(require_permission(Permission.ATTENDANCE_VIEW))])
def download_application_attachment(application_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    application = _get_application(db, application_id)
    episode = _get_episode(db, application.episode_id)
    _check_scope(db, user, episode)
    if not application.attachment_object_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No attachment uploaded for this application")
    return FileResponse(leave_service.attachment_path(application), filename=application.attachment_file_name)


@router.get("/history/{episode_id}", dependencies=[Depends(require_permission(Permission.ATTENDANCE_VIEW))])
def get_history(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    rows = leave_service.leave_history(db, episode_id)
    return [_application_dict(a) for a in rows]
