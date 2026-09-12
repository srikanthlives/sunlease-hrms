from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import (
    AttendanceRecord, DocumentMeta, EmploymentEpisode, LeaveApplication, LeaveType, Payslip, User,
)
from app.schemas.attendance import AttendanceRequestIn
from app.schemas.leave import LeaveApplicationIn
from app.services import attendance_service, document_service, leave_service

from app.routers import attendance as attendance_router
from app.routers import employees as employees_router
from app.routers import leave as leave_router
from app.routers import payroll as payroll_router

router = APIRouter(prefix="/api/v1/me", tags=["me"], dependencies=[Depends(get_current_user)])


def _my_episode(db: Session, user: User) -> EmploymentEpisode:
    """Resolves the caller's own EmploymentEpisode from their User.employee_id
    - never from a client-supplied episode_id. A login not linked to an
    Employee (employee_id is null) gets a plain 404, same as any other
    'nothing here for you' case - not a permission leak."""
    if not user.employee_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No employee record linked to this login")
    episode = (
        db.query(EmploymentEpisode)
        .filter(EmploymentEpisode.employee_id == user.employee_id)
        .order_by(EmploymentEpisode.date_of_joining.desc())
        .first()
    )
    if not episode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No employee record linked to this login")
    return episode


@router.get("/profile")
def my_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    return employees_router.build_employee_detail(db, user, episode)


def _my_document(db: Session, episode: EmploymentEpisode, document_id: int) -> DocumentMeta:
    document = db.query(DocumentMeta).filter(DocumentMeta.id == document_id, DocumentMeta.episode_id == episode.id).first()
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


@router.get("/documents/{document_id}/preview")
def my_document_preview(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    document = _my_document(db, episode, document_id)
    path = document_service.resolve_file_path(document)
    return FileResponse(path, media_type=document.mime_type)


@router.get("/documents/{document_id}/download")
def my_document_download(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    document = _my_document(db, episode, document_id)
    path = document_service.resolve_file_path(document)
    return FileResponse(path, filename=document.file_name, media_type=document.mime_type)


@router.get("/leave/balances")
def my_leave_balances(year: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    year = year or date.today().year
    leave_types = db.query(LeaveType).filter(LeaveType.is_active.is_(True)).all()
    balances = []
    for lt in leave_types:
        balance = leave_service.get_or_create_balance(db, episode.id, lt.id, year)
        d = leave_service.balance_dict(balance)
        d["leave_type_code"] = lt.code
        d["leave_type_name"] = lt.name
        balances.append(d)
    db.commit()
    return balances


@router.post("/leave/applications")
def my_apply_leave(payload: LeaveApplicationIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    application = leave_service.apply_leave(
        db, episode.id, payload.leave_type_id, payload.start_date, payload.end_date,
        payload.is_half_day, payload.half_day_session, payload.reason, user,
    )
    db.commit()
    return {"ok": True, "id": application.id, "status": application.status, "days": application.days}


@router.get("/leave/applications")
def my_leave_applications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    rows = (
        db.query(LeaveApplication)
        .filter(LeaveApplication.episode_id == episode.id)
        .order_by(LeaveApplication.created_at.desc())
        .all()
    )
    return [leave_router._application_dict(a) for a in rows]


def _my_application(db: Session, episode: EmploymentEpisode, application_id: int) -> LeaveApplication:
    application = (
        db.query(LeaveApplication)
        .filter(LeaveApplication.id == application_id, LeaveApplication.episode_id == episode.id)
        .first()
    )
    if not application:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave application not found")
    return application


@router.post("/leave/applications/{application_id}/cancel")
def my_cancel_leave(application_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    _my_application(db, episode, application_id)
    leave_service.cancel_leave(db, application_id, user)
    db.commit()
    return {"ok": True}


@router.post("/leave/applications/{application_id}/attachment")
def my_upload_leave_attachment(
    application_id: int, file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    episode = _my_episode(db, user)
    application = _my_application(db, episode, application_id)
    leave_service.save_attachment(db, application, file, user)
    db.commit()
    return {"ok": True, "attachment_file_name": application.attachment_file_name}


@router.get("/leave/applications/{application_id}/attachment")
def my_download_leave_attachment(application_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    application = _my_application(db, episode, application_id)
    if not application.attachment_object_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No attachment uploaded for this application")
    return FileResponse(leave_service.attachment_path(application), filename=application.attachment_file_name)


@router.get("/attendance/records")
def my_attendance_records(start_date: date, end_date: date, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    rows = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.episode_id == episode.id, AttendanceRecord.date >= start_date, AttendanceRecord.date <= end_date)
        .order_by(AttendanceRecord.date)
        .all()
    )
    return [attendance_router._record_dict(r) for r in rows]


@router.post("/attendance/requests")
def my_create_attendance_request(payload: AttendanceRequestIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    request = attendance_service.request_attendance_change(
        db, episode.id, payload.date, payload.request_type, payload.requested_check_in,
        payload.requested_check_out, payload.requested_overtime_minutes, payload.reason, user,
    )
    db.commit()
    return {"ok": True, "id": request.id}


@router.get("/payslips")
def my_payslips(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    rows = (
        db.query(Payslip)
        .filter(Payslip.episode_id == episode.id)
        .order_by(Payslip.generated_at.desc())
        .all()
    )
    return [payroll_router._payslip_summary_dict(p) for p in rows]


@router.get("/payslips/{payslip_id}")
def my_payslip_detail(payslip_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _my_episode(db, user)
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id, Payslip.episode_id == episode.id).first()
    if not payslip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payslip not found")
    return payroll_router.build_payslip_detail(db, payslip)
