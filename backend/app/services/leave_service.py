import datetime as dt
import os
import re

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import AuditAction, TransactionType
from app.models.models import (
    LeaveType, LeaveEligibilityRule, LeaveBalance, LeaveApplication,
    RosterEntry, EmploymentEpisode, User,
)
from app.services import audit_service, approval_service, document_service


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip()).strip("-").lower()
    return value or "file"


def save_attachment(db: Session, application: LeaveApplication, upload_file: UploadFile, actor: User) -> LeaveApplication:
    """Local-disk supporting-document upload for a leave application (e.g.
    a medical certificate for Sick Leave) - mirrors
    document_service.save_upload's UPLOAD_DIR pattern, kept separate since
    leave attachments aren't a DocumentType/DocumentMeta (they're
    per-application, not per-episode-per-type)."""
    ext = os.path.splitext(upload_file.filename or "")[1]
    target_dir = os.path.join(document_service._employee_upload_dir(db, application.episode), "leave-attachments")
    os.makedirs(target_dir, exist_ok=True)
    stored_name = f"{application.id}-{_slug(os.path.splitext(upload_file.filename or '')[0])}{ext}"
    full_path = os.path.join(target_dir, stored_name)

    content = upload_file.file.read()
    with open(full_path, "wb") as f:
        f.write(content)

    application.attachment_object_key = os.path.relpath(full_path, settings.UPLOAD_DIR)
    application.attachment_file_name = upload_file.filename
    db.add(application)
    audit_service.record(db, "LEAVE_APPLICATION", application.id, AuditAction.UPDATE, actor, new_value="attachment uploaded")
    return application


def attachment_path(application: LeaveApplication) -> str:
    return os.path.join(settings.UPLOAD_DIR, application.attachment_object_key)


def find_eligibility_rule(db: Session, leave_type_id: int, episode: EmploymentEpisode) -> LeaveEligibilityRule | None:
    """Most-specific-first match: cost_center+category -> cost_center-only
    -> category-only -> global fallback. Mirrors
    approval_service.find_approval_rule's cascade."""
    cost_center_id = approval_service.current_cost_center_id(db, episode.id)
    employee_category_id = episode.employee_category_id

    candidates = db.query(LeaveEligibilityRule).filter(LeaveEligibilityRule.leave_type_id == leave_type_id).all()
    ranked = []
    for rule in candidates:
        cc_match = rule.cost_center_id is None or rule.cost_center_id == cost_center_id
        cat_match = rule.employee_category_id is None or rule.employee_category_id == employee_category_id
        if not (cc_match and cat_match):
            continue
        specificity = (rule.cost_center_id is not None) + (rule.employee_category_id is not None)
        ranked.append((specificity, rule))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked[0][1]


def get_or_create_balance(db: Session, episode_id: int, leave_type_id: int, year: int, as_of: dt.date | None = None) -> LeaveBalance:
    as_of = as_of or dt.date.today()
    balance = (
        db.query(LeaveBalance)
        .filter(LeaveBalance.episode_id == episode_id, LeaveBalance.leave_type_id == leave_type_id, LeaveBalance.year == year)
        .first()
    )
    if not balance:
        balance = LeaveBalance(episode_id=episode_id, leave_type_id=leave_type_id, year=year, opening_balance=0, accrued=0, used=0, adjusted=0)
        db.add(balance)
        db.flush()

    leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id).first()
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == episode_id).first()

    if leave_type and leave_type.accrual_frequency == "YEARLY":
        rule = find_eligibility_rule(db, leave_type_id, episode) if episode else None
        if rule:
            balance.accrued = rule.annual_entitlement
    elif leave_type and leave_type.accrual_frequency == "MONTHLY":
        if as_of.year == year:
            months_elapsed = min(12, as_of.month)
        elif as_of.year > year:
            months_elapsed = 12
        else:
            months_elapsed = 0
        balance.accrued = (leave_type.accrual_amount or 0) * months_elapsed

    db.add(balance)
    return balance


def balance_dict(balance: LeaveBalance) -> dict:
    available = (balance.opening_balance or 0) + (balance.accrued or 0) + (balance.adjusted or 0) - (balance.used or 0)
    return {
        "id": balance.id, "episode_id": balance.episode_id, "leave_type_id": balance.leave_type_id, "year": balance.year,
        "opening_balance": balance.opening_balance, "accrued": balance.accrued, "used": balance.used,
        "adjusted": balance.adjusted, "available": available,
    }


def _is_pure_off_range(db: Session, episode_id: int, start_date: dt.date, end_date: dt.date) -> bool:
    """True if every date in the range has a RosterEntry marked
    weekly-off/holiday (missing RosterEntry rows are not treated as off)."""
    entries = {
        r.date: r
        for r in db.query(RosterEntry).filter(
            RosterEntry.episode_id == episode_id, RosterEntry.date >= start_date, RosterEntry.date <= end_date,
        ).all()
    }
    current = start_date
    any_day = False
    while current <= end_date:
        any_day = True
        row = entries.get(current)
        if not row or not (row.is_weekly_off or row.is_holiday):
            return False
        current += dt.timedelta(days=1)
    return any_day


def apply_leave(
    db: Session, episode_id: int, leave_type_id: int, start_date: dt.date, end_date: dt.date,
    is_half_day: bool, half_day_session: str | None, reason: str | None, user: User,
) -> LeaveApplication:
    leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id).first()
    if not leave_type:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave type not found")

    if not is_half_day and _is_pure_off_range(db, episode_id, start_date, end_date):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot apply leave on a weekly-off/holiday day")

    days = 0.5 if (is_half_day and start_date == end_date) else float((end_date - start_date).days + 1)

    balance = get_or_create_balance(db, episode_id, leave_type_id, start_date.year)
    available = (balance.opening_balance or 0) + (balance.accrued or 0) + (balance.adjusted or 0) - (balance.used or 0)
    if days > available:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Insufficient leave balance: requested {days:g}, available {available:g}")

    application = LeaveApplication(
        episode_id=episode_id, leave_type_id=leave_type_id, start_date=start_date, end_date=end_date,
        is_half_day=is_half_day, half_day_session=half_day_session, days=days, reason=reason,
        status="PENDING",
    )
    db.add(application)
    db.flush()

    if not leave_type.requires_approval:
        application.status = "APPROVED"
        application.reviewed_by_id = user.id
        application.reviewed_at = dt.datetime.utcnow()
        balance.used = (balance.used or 0) + days
        db.add(balance)
        db.add(application)

    audit_service.record(db, "LEAVE_APPLICATION", application.id, AuditAction.CREATE, user, new_value=application.status)
    return application


def review_leave_application(db: Session, application_id: int, user: User, approve: bool, remarks: str | None) -> LeaveApplication:
    application = db.query(LeaveApplication).filter(LeaveApplication.id == application_id).first()
    if not application:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave application not found")
    if application.status != "PENDING":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This leave application has already been reviewed")

    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == application.episode_id).first()
    if not episode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee record not found")
    approval_service.authorize_approval(db, user, episode, TransactionType.LEAVE_APPLICATION)

    application.reviewed_by_id = user.id
    application.reviewed_at = dt.datetime.utcnow()
    application.review_remarks = remarks

    if approve:
        balance = get_or_create_balance(db, application.episode_id, application.leave_type_id, application.start_date.year)
        balance.used = (balance.used or 0) + application.days
        db.add(balance)
        application.status = "APPROVED"
        audit_service.record(db, "LEAVE_APPLICATION", application.id, AuditAction.APPROVE, user)
    else:
        application.status = "REJECTED"
        audit_service.record(db, "LEAVE_APPLICATION", application.id, AuditAction.REJECT, user, new_value=remarks)

    db.add(application)
    return application


def cancel_leave(db: Session, application_id: int, user: User) -> LeaveApplication:
    application = db.query(LeaveApplication).filter(LeaveApplication.id == application_id).first()
    if not application:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave application not found")

    can_cancel = application.status == "PENDING" or (
        application.status == "APPROVED" and application.start_date > dt.date.today()
    )
    if not can_cancel:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a pending application, or an approved future one, can be cancelled")

    if application.status == "APPROVED":
        balance = get_or_create_balance(db, application.episode_id, application.leave_type_id, application.start_date.year)
        balance.used = max(0, (balance.used or 0) - application.days)
        db.add(balance)

    application.status = "CANCELLED"
    db.add(application)
    audit_service.record(db, "LEAVE_APPLICATION", application.id, AuditAction.UPDATE, user, new_value="CANCELLED")
    return application


def leave_history(db: Session, episode_id: int) -> list[LeaveApplication]:
    return (
        db.query(LeaveApplication)
        .filter(LeaveApplication.episode_id == episode_id)
        .order_by(LeaveApplication.start_date.desc())
        .all()
    )
