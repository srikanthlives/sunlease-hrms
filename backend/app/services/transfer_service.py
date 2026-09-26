"""Cost Center transfer of an existing employee.

A Cost Center change is not an edit - it closes the person's stint in the old
Cost Center (exit formalities, the exit approved by that side's approver) and
opens a new stint in the new one (entry formalities, approved by the
destination approver). Same Employee (person), new EmploymentEpisode, new
employee number unless they served that Cost Center before (then the old
number comes back, like a rejoin). History - profile, attendance, payroll -
stays on the old stint in the old Cost Center; the new stint builds its own.

INTERNAL transfers keep service continuous (leave usage and service start
carry over, no final settlement); RESIGNATION ones are a real exit followed by
a fresh joining (no continuity, final settlement handled the normal way).
"""
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.enums import AuditAction, EpisodeStatus
from app.models.models import EmployeeTransfer, EmploymentEpisode, SeparationRecord, User
from app.services import audit_service, employee_service

INTERNAL = "INTERNAL"
RESIGNATION = "RESIGNATION"
INITIATED = "INITIATED"
COMPLETED = "COMPLETED"
CANCELLED = "CANCELLED"


def open_transfer_for(db: Session, episode_id: int) -> EmployeeTransfer | None:
    """The in-progress transfer this stint is either leaving (from) or
    entering (to), if any."""
    return (
        db.query(EmployeeTransfer)
        .filter(EmployeeTransfer.status == INITIATED)
        .filter((EmployeeTransfer.from_episode_id == episode_id) | (EmployeeTransfer.to_episode_id == episode_id))
        .first()
    )


def initiate_transfer(
    db: Session, episode: EmploymentEpisode, *, transfer_type: str, cost_center_id: int, project_id: int, department_id: int,
    transfer_date: date, employee_number: str | None, remarks: str | None, user: User,
) -> EmployeeTransfer:
    if transfer_type not in (INTERNAL, RESIGNATION):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Transfer type must be INTERNAL or RESIGNATION")
    if episode.status != EpisodeStatus.ACTIVE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only an Active employee can be transferred")
    if db.query(EmployeeTransfer).filter(EmployeeTransfer.employee_id == episode.employee_id, EmployeeTransfer.status == INITIATED).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A transfer is already in progress for this employee")
    home = employee_service.home_cost_center_id(db, episode.id)
    if home == cost_center_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Already in this Cost Center - change the Project/Department directly instead")
    if episode.date_of_joining and transfer_date <= episode.date_of_joining:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Transfer date must be after the current joining date")

    last_working = transfer_date - timedelta(days=1)
    internal = transfer_type == INTERNAL
    # Build the destination stint first - it validates project/department and
    # the employee number, so a bad request leaves the current stint untouched.
    new = employee_service.create_new_stint(
        db, episode, transfer_date, cost_center_id, project_id, department_id, employee_number, continuous_service=internal,
    )

    record = db.query(SeparationRecord).filter(SeparationRecord.episode_id == episode.id).first()
    if not record:
        record = SeparationRecord(episode_id=episode.id)
        db.add(record)
    record.separation_type = "INTERNAL_TRANSFER" if internal else "RESIGNATION"
    record.last_working_date = last_working
    record.reason = "Internal transfer to another Cost Center" if internal else "Resignation - joining another Cost Center"
    record.remarks = remarks
    # Internal transfer: leave/gratuity are retained on the new stint, so no
    # final settlement is due. Resignation: Full & Final is calculated
    # automatically when the exit is approved (employees.complete_separation).
    record.full_final_status = "NOT_REQUIRED" if internal else "PENDING"

    old_status = episode.status
    episode.status = EpisodeStatus.NOTICE_PERIOD
    episode.separation_date = last_working
    episode.separation_reason = record.reason
    db.add(episode)

    transfer = EmployeeTransfer(
        employee_id=episode.employee_id, from_episode_id=episode.id, to_episode_id=new.id,
        from_cost_center_id=home, to_cost_center_id=cost_center_id, transfer_type=transfer_type,
        transfer_date=transfer_date, status=INITIATED, remarks=remarks, initiated_by_id=user.id,
    )
    db.add(transfer)
    db.flush()
    audit_service.record(db, "SEPARATION", episode.id, AuditAction.STATUS_CHANGE, user, old_value=old_status, new_value=f"{episode.status} (transfer)")
    audit_service.record(
        db, "EMPLOYEE_TRANSFER", transfer.id, AuditAction.CREATE, user,
        new_value=f"{transfer_type} transfer from cost center {home} (episode {episode.id}) to {cost_center_id} (episode {new.id}, number {new.employee_number}) effective {transfer_date}",
    )
    return transfer


def cancel_transfer(db: Session, transfer: EmployeeTransfer, user: User) -> None:
    """Only while the exit isn't completed yet - reverts the old stint to
    Active and removes the destination draft."""
    if transfer.status != INITIATED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This transfer is not in progress")
    old = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == transfer.from_episode_id).first()
    if old.status != EpisodeStatus.NOTICE_PERIOD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The exit has already been completed - the transfer can no longer be cancelled")
    new = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == transfer.to_episode_id).first() if transfer.to_episode_id else None
    if new and new.status not in (EpisodeStatus.DRAFT, EpisodeStatus.PENDING_APPROVAL):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The new employment record has already been approved")

    old.status = EpisodeStatus.ACTIVE
    old.separation_date = None
    old.separation_reason = None
    db.add(old)
    transfer.status = CANCELLED
    transfer.to_episode_id = None
    db.add(transfer)
    db.flush()
    if new:
        new.status = EpisodeStatus.DRAFT
        db.flush()
        employee_service.purge_draft_episode(db, new)
    audit_service.record(db, "EMPLOYEE_TRANSFER", transfer.id, AuditAction.UPDATE, user, old_value=INITIATED, new_value=CANCELLED)


def gate_entry_approval(db: Session, episode: EmploymentEpisode) -> None:
    """The destination stint can't go live until the exit from the old Cost
    Center is completed - a person never has two live records."""
    t = db.query(EmployeeTransfer).filter(EmployeeTransfer.to_episode_id == episode.id, EmployeeTransfer.status == INITIATED).first()
    if not t:
        return
    old = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == t.from_episode_id).first()
    if old.status != EpisodeStatus.SEPARATED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete and approve the exit from the previous Cost Center first")


def complete_on_entry_approval(db: Session, episode: EmploymentEpisode, user: User) -> None:
    t = db.query(EmployeeTransfer).filter(EmployeeTransfer.to_episode_id == episode.id, EmployeeTransfer.status == INITIATED).first()
    if not t:
        return
    t.status = COMPLETED
    t.completed_at = datetime.utcnow()
    db.add(t)
    audit_service.record(db, "EMPLOYEE_TRANSFER", t.id, AuditAction.UPDATE, user, old_value=INITIATED, new_value=COMPLETED)
