import io
import json
import os
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.enums import AddressType, AuditAction, EpisodeStatus, Permission, RoleName, TransactionType
from app.models.models import (
    Employee, Address, EmploymentEpisode, StatutoryInfo, BankAccount, Dependent, Nominee,
    SeparationRecord, ChangeRequest, AuditLog, User, OrgAssignment, CostAllocation, CostCenter, Department,
    DocumentMeta, DrivingLicenceDetail,
)
from app.schemas.employees import (
    PersonalInfoStep, AddressStep, EmploymentInfoStep, OrgAssignmentStep, CostAllocationIn,
    StatutoryInfoStep, BankAccountStep, DependentIn, NomineeIn, SeparationIn, SeparationChecklistUpdate,
    ChangeRequestReview, DrivingLicenceStep,
)
from app.services import (
    audit_service, employee_service, approval_service, permission_service,
    document_service, licence_service, bulk_import_service,
)

router = APIRouter(prefix="/api/v1/employees", tags=["employees"], dependencies=[Depends(get_current_user)])


def _get_episode(db: Session, episode_id: int) -> EmploymentEpisode:
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == episode_id).first()
    if not episode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee record not found")
    return episode


def _address_dict(employee: Employee) -> dict:
    """Flattens the employee's PRESENT/PERMANENT Address rows into the
    present_*/permanent_* shape the frontend's Address step edits."""
    by_type = {a.address_type: a for a in employee.addresses}
    result = {"same_as_present": False}
    for prefix, addr_type in (("present", AddressType.PRESENT), ("permanent", AddressType.PERMANENT)):
        addr = by_type.get(addr_type)
        for field in ("line1", "line2", "city", "state", "pincode", "country"):
            result[f"{prefix}_{field}"] = getattr(addr, field) if addr else None
    present = by_type.get(AddressType.PRESENT)
    permanent = by_type.get(AddressType.PERMANENT)
    if present and permanent:
        result["same_as_present"] = all(
            getattr(present, f) == getattr(permanent, f) for f in ("line1", "line2", "city", "state", "pincode", "country")
        )
    return result


def _driving_licence_dict(episode: EmploymentEpisode) -> dict:
    record = episode.driving_licence
    if not record:
        return {"licence_number": None, "badge_number": None, "vehicle_class": None, "issuing_authority": None, "issue_date": None, "expiry_date": None}
    return {
        "licence_number": record.licence_number, "badge_number": record.badge_number, "vehicle_class": record.vehicle_class,
        "issuing_authority": record.issuing_authority, "issue_date": record.issue_date, "expiry_date": record.expiry_date,
    }


def _check_scope(db: Session, user: User, episode: EmploymentEpisode):
    """403s if the episode's current Cost Center is outside the user's
    UserCostCenterScope (blueprint §18). HR_ADMIN is always unrestricted."""
    cc_id = approval_service.current_cost_center_id(db, episode.id)
    if not permission_service.can_see_cost_center(db, user, cc_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This employee is outside your Cost Center scope")


def _save_or_request(db: Session, episode: EmploymentEpisode, transaction_type: str, changes: dict, user: User):
    """Applies directly when the actor is allowed to (HR_ADMIN, or the
    episode isn't ACTIVE yet), otherwise creates a ChangeRequest instead -
    same branching sunlease-expms uses for direct-edit vs edit-request,
    see services/approval_service.py."""
    if user.role.name == RoleName.HR_ADMIN or episode.status != EpisodeStatus.ACTIVE:
        approval_service.apply_changes(db, episode, transaction_type, changes)
        audit_service.record(db, transaction_type, episode.id, AuditAction.UPDATE, user)
        db.commit()
        return {"ok": True, "submitted_for_approval": False}

    request = approval_service.create_change_request(db, episode, transaction_type, changes, user)
    db.commit()
    return {"ok": True, "submitted_for_approval": True, "change_request_id": request.id}


@router.post("/draft", dependencies=[Depends(require_permission(Permission.EMPLOYEE_CREATE))])
def create_draft(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    employee = Employee(first_name="", last_name="")
    db.add(employee)
    db.flush()

    # Placeholder employee_number until the Employment Info step sets the real one.
    episode = EmploymentEpisode(employee_id=employee.id, employee_number=f"DRAFT-{employee.id}", status=EpisodeStatus.DRAFT)
    db.add(episode)
    db.flush()

    audit_service.record(db, "EMPLOYEE_DRAFT", episode.id, AuditAction.CREATE, user)
    db.commit()
    db.refresh(episode)
    return {"employee_id": employee.id, "episode_id": episode.id}


@router.get("-bulk-upload-template", dependencies=[Depends(require_permission(Permission.EMPLOYEE_CREATE))])
def download_bulk_upload_template(db: Session = Depends(get_db)):
    """Downloadable .xlsx: header row (all supported fields) + one filled
    example row, plus a Reference Values sheet listing the exact Cost
    Center/Department/Project/Category/Employment Type/Designation/Work
    Location names configured in Organization Setup - see
    services/bulk_import_service.py."""
    wb = bulk_import_service.build_template_workbook(db)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=hrms_employee_bulk_upload_template.xlsx"},
    )


@router.post("-bulk-upload", dependencies=[Depends(require_permission(Permission.EMPLOYEE_CREATE))])
def bulk_upload_employees(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Each valid row creates a Draft Employee + EmploymentEpisode - same
    starting point as clicking "New Employee" once per row, with as much
    of Personal/Address/Employment/Organizational Assignment filled in as
    the row provides. Statutory/Bank/Documents/Dependents/Nominees/Driving
    Licence are completed per-employee afterwards via the wizard."""
    content = file.file.read()
    result = bulk_import_service.import_workbook(db, content, user)
    db.commit()
    return result


@router.get("", dependencies=[Depends(require_permission(Permission.EMPLOYEE_VIEW))])
def list_employees(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episodes = (
        db.query(EmploymentEpisode)
        .options(
            joinedload(EmploymentEpisode.employee),
            joinedload(EmploymentEpisode.employee_category),
            joinedload(EmploymentEpisode.employee_type),
            joinedload(EmploymentEpisode.designation),
            joinedload(EmploymentEpisode.work_location),
        )
        .order_by(EmploymentEpisode.id.desc())
        .all()
    )

    # Bulk-fetch the currently-open assignment per episode (and the Cost
    # Center/Department names it points at) instead of one query per row.
    open_assignments = db.query(OrgAssignment).filter(OrgAssignment.effective_to.is_(None)).all()
    assignment_by_episode = {a.episode_id: a for a in open_assignments}
    cost_centers = {c.id: c.name for c in db.query(CostCenter.id, CostCenter.name).all()}
    departments = {d.id: d.name for d in db.query(Department.id, Department.name).all()}

    rows = []
    for e in episodes:
        assignment = assignment_by_episode.get(e.id)
        cc_id = assignment.cost_center_id if assignment else None
        if not permission_service.can_see_cost_center(db, user, cc_id):
            continue
        rows.append({
            "episode_id": e.id,
            "employee_id": e.employee_id,
            "employee_number": e.employee_number,
            "first_name": e.employee.first_name,
            "last_name": e.employee.last_name,
            "gender": e.employee.gender,
            "mobile_number": e.employee.mobile_number,
            "official_email": e.employee.official_email,
            "designation": e.designation.name if e.designation else None,
            "employment_type": e.employee_type.name if e.employee_type else None,
            "employee_category": e.employee_category.name if e.employee_category else None,
            "date_of_joining": e.date_of_joining,
            "work_location": e.work_location.name if e.work_location else None,
            "cost_center": cost_centers.get(cc_id),
            "department": departments.get(assignment.department_id) if assignment else None,
            "status": e.status,
        })
    return rows


@router.get("/{episode_id}", dependencies=[Depends(require_permission(Permission.EMPLOYEE_VIEW))])
def get_employee(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    detail = {
        "episode": {
            "id": episode.id,
            "employee_number": episode.employee_number,
            "employment_type_id": episode.employment_type_id,
            "employment_type": episode.employee_type.name if episode.employee_type else None,
            "employee_category_id": episode.employee_category_id,
            "employee_category": episode.employee_category.name if episode.employee_category else None,
            "designation_id": episode.designation_id,
            "designation": episode.designation.name if episode.designation else None,
            "work_location_id": episode.work_location_id,
            "work_location": episode.work_location.name if episode.work_location else None,
            "shift_group": episode.shift_group,
            "date_of_joining": episode.date_of_joining,
            "confirmation_date": episode.confirmation_date,
            "status": episode.status,
            "separation_date": episode.separation_date,
            "separation_reason": episode.separation_reason,
        },
        "employee": {
            "id": episode.employee.id,
            "has_photo": bool(episode.employee.photo_object_key),
            "first_name": episode.employee.first_name,
            "middle_name": episode.employee.middle_name,
            "last_name": episode.employee.last_name,
            "father_husband_name": episode.employee.father_husband_name,
            "gender": episode.employee.gender,
            "date_of_birth": episode.employee.date_of_birth,
            "marital_status": episode.employee.marital_status,
            "educational_qualification": episode.employee.educational_qualification,
            "mobile_number": episode.employee.mobile_number,
            "alternate_mobile_number": episode.employee.alternate_mobile_number,
            "personal_email": episode.employee.personal_email,
            "official_email": episode.employee.official_email,
            "emergency_contact_name": episode.employee.emergency_contact_name,
            "emergency_contact_relationship": episode.employee.emergency_contact_relationship,
            "emergency_contact_mobile": episode.employee.emergency_contact_mobile,
            "aadhaar": episode.employee.aadhaar,
            "pan": episode.employee.pan,
            "previous_designation": episode.employee.previous_designation,
            "previous_company_name": episode.employee.previous_company_name,
            "previous_company_details": episode.employee.previous_company_details,
            "previous_date_of_joining": episode.employee.previous_date_of_joining,
            "total_experience_years": episode.employee.total_experience_years,
        },
        "address": _address_dict(episode.employee),
        "driving_licence": _driving_licence_dict(episode),
        "assignments": [
            {
                "id": a.id, "cost_center_id": a.cost_center_id, "project_id": a.project_id,
                "department_id": a.department_id, "effective_from": a.effective_from, "effective_to": a.effective_to,
            } for a in episode.assignments
        ],
        "allocations": [
            {
                "id": a.id, "cost_center_id": a.cost_center_id, "project_id": a.project_id,
                "cost_center_name": a.cost_center.name if a.cost_center else None,
                "project_name": a.project.name if a.project else None,
                "percentage": a.percentage, "effective_from": a.effective_from, "effective_to": a.effective_to,
            } for a in episode.allocations
        ],
        "statutory": [
            {
                "id": s.id,
                "pf_eligible": s.pf_eligible, "pf_name_on_file": s.pf_name_on_file,
                "uan": s.uan, "pf_effective_date": s.pf_effective_date,
                "esi_eligible": s.esi_eligible, "esi_name_on_file": s.esi_name_on_file,
                "esi_number": s.esi_number, "esi_mediclaim_number": s.esi_mediclaim_number,
                "esi_effective_date": s.esi_effective_date,
                "pt_eligible": s.pt_eligible, "gratuity_eligible": s.gratuity_eligible,
                "effective_from": s.effective_from, "effective_to": s.effective_to,
            } for s in episode.statutory_records
        ],
        "bank_accounts": [
            {
                "id": b.id, "bank_name": b.bank_name, "account_number": b.account_number,
                "ifsc": b.ifsc, "is_primary": b.is_primary, "verification_status": b.verification_status,
            } for b in episode.bank_accounts
        ],
        "dependents": [{"id": d.id, "name": d.name, "relationship_type": d.relationship_type} for d in episode.dependents],
        "nominees": [{"id": n.id, "name": n.name, "nomination_type": n.nomination_type, "percentage": n.percentage} for n in episode.nominees],
        "documents": [
            {
                "id": d.id, "document_type_id": d.document_type_id, "document_type": d.document_type,
                "file_name": d.file_name, "file_size": d.file_size, "verification_status": d.verification_status,
                "created_at": d.created_at,
            } for d in episode.documents
        ],
        "separation": _separation_dict(episode),
    }
    return permission_service.mask_sensitive_fields(db, user, detail)


@router.put("/{episode_id}/personal", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def save_personal_info(episode_id: int, payload: PersonalInfoStep, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    return _save_or_request(db, episode, TransactionType.IDENTITY_CHANGE, payload.model_dump(), user)


@router.put("/{episode_id}/address", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def save_address(episode_id: int, payload: AddressStep, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Upserts the employee's PRESENT and (unless same_as_present) a
    separate PERMANENT Address row. Not effective-dated and not routed
    through ChangeRequest - addresses have no historical-tracking
    requirement in the blueprint, so this always applies directly."""
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    employee = episode.employee

    fields = ("line1", "line2", "city", "state", "pincode", "country")
    present_values = {f: getattr(payload, f"present_{f}") for f in fields}
    permanent_values = present_values if payload.same_as_present else {f: getattr(payload, f"permanent_{f}") for f in fields}

    for addr_type, values in ((AddressType.PRESENT, present_values), (AddressType.PERMANENT, permanent_values)):
        row = db.query(Address).filter(Address.employee_id == employee.id, Address.address_type == addr_type).first()
        if not row:
            row = Address(employee_id=employee.id, address_type=addr_type)
        for field, value in values.items():
            setattr(row, field, value)
        db.add(row)

    audit_service.record(db, "ADDRESS", employee.id, AuditAction.UPDATE, user)
    db.commit()
    return {"ok": True}


@router.put("/{episode_id}/employment", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def save_employment_info(episode_id: int, payload: EmploymentInfoStep, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)

    if payload.employee_number != episode.employee_number:
        existing = db.query(EmploymentEpisode).filter(
            EmploymentEpisode.employee_number == payload.employee_number,
            EmploymentEpisode.id != episode.id,
        ).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "Employee Number already in use")

    return _save_or_request(db, episode, TransactionType.EMPLOYMENT_CHANGE, payload.model_dump(), user)


@router.post("/{episode_id}/assignment", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def save_org_assignment(episode_id: int, payload: OrgAssignmentStep, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    employee_service.add_org_assignment(db, episode.id, payload.model_dump())
    audit_service.record(db, "ORG_ASSIGNMENT", episode.id, AuditAction.CREATE, user)
    db.commit()
    return {"ok": True}


@router.post("/{episode_id}/allocation", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def save_cost_allocation(episode_id: int, payload: CostAllocationIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)

    current_total = employee_service.active_allocation_total(db, episode.id)
    if current_total + payload.percentage > 100.01:  # small epsilon for float rounding
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Active allocations already total {current_total:g}% - adding {payload.percentage:g}% would exceed 100%",
        )

    employee_service.add_cost_allocation(db, episode.id, payload.model_dump())
    audit_service.record(db, "COST_ALLOCATION", episode.id, AuditAction.CREATE, user)
    db.commit()
    return {"ok": True, "active_total_percentage": employee_service.active_allocation_total(db, episode.id)}


@router.delete("/{episode_id}/allocation/{allocation_id}", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def delete_cost_allocation(episode_id: int, allocation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    allocation = db.query(CostAllocation).filter(CostAllocation.id == allocation_id, CostAllocation.episode_id == episode.id).first()
    if not allocation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cost allocation not found")
    db.delete(allocation)
    audit_service.record(db, "COST_ALLOCATION", episode.id, AuditAction.UPDATE, user, old_value=f"removed allocation {allocation_id}")
    db.commit()
    return {"ok": True, "active_total_percentage": employee_service.active_allocation_total(db, episode.id)}


@router.post("/{episode_id}/statutory", dependencies=[Depends(require_permission(Permission.EMPLOYEE_SENSITIVE_EDIT))])
def save_statutory(episode_id: int, payload: StatutoryInfoStep, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    # effective_from is a record-capture marker, not user input now that PF
    # and ESI each carry their own effective date (pf_effective_date/
    # esi_effective_date) - see StatutoryInfoStep.
    db.add(StatutoryInfo(episode_id=episode.id, effective_from=date.today(), **payload.model_dump()))
    audit_service.record(db, "STATUTORY_INFO", episode.id, AuditAction.CREATE, user)
    db.commit()
    return {"ok": True}


@router.post("/{episode_id}/bank", dependencies=[Depends(require_permission(Permission.EMPLOYEE_SENSITIVE_EDIT))])
def save_bank_account(episode_id: int, payload: BankAccountStep, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    db.add(BankAccount(episode_id=episode.id, **payload.model_dump()))
    audit_service.record(db, "BANK_ACCOUNT", episode.id, AuditAction.CREATE, user)
    db.commit()
    return {"ok": True}


@router.get("/{episode_id}/driving-licence-requirement", dependencies=[Depends(require_permission(Permission.EMPLOYEE_VIEW))])
def get_driving_licence_requirement(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Whether the wizard's Driving Licence step should be shown for this
    employee, per Document Configuration-style Employee Type/Category/
    Designation rules (see services/licence_service.py)."""
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    return licence_service.resolve_driving_licence_requirement(db, episode)


@router.put("/{episode_id}/driving-licence", dependencies=[Depends(require_permission(Permission.EMPLOYEE_SENSITIVE_EDIT))])
def save_driving_licence(episode_id: int, payload: DrivingLicenceStep, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    record = db.query(DrivingLicenceDetail).filter(DrivingLicenceDetail.episode_id == episode.id).first()
    if not record:
        record = DrivingLicenceDetail(episode_id=episode.id)
        db.add(record)
    for field, value in payload.model_dump().items():
        setattr(record, field, value)
    audit_service.record(db, "DRIVING_LICENCE", episode.id, AuditAction.UPDATE, user)
    db.commit()
    return {"ok": True}


@router.put("/{episode_id}/photo", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def upload_photo(episode_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    document_service.save_employee_photo(db, episode, file)
    audit_service.record(db, "EMPLOYEE_PHOTO", episode.employee_id, AuditAction.UPDATE, user)
    db.commit()
    return {"ok": True}


@router.get("/{episode_id}/photo", dependencies=[Depends(require_permission(Permission.EMPLOYEE_VIEW))])
def get_photo(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    path = document_service.resolve_employee_photo_path(episode.employee)
    if not path or not os.path.exists(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo uploaded")
    return FileResponse(path)


@router.get("/{episode_id}/required-documents", dependencies=[Depends(require_permission(Permission.EMPLOYEE_DOCUMENTS_VIEW))])
def get_required_documents(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Resolves which documents this employee needs to upload, per the
    Document Configuration rules (blueprint §14) matched against their
    Employee Type / Category / Designation - see
    services/document_service.py::resolve_required_documents."""
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    return document_service.resolve_required_documents(db, episode)


@router.post("/{episode_id}/documents", dependencies=[Depends(require_permission(Permission.EMPLOYEE_DOCUMENTS_UPLOAD))])
def upload_document(
    episode_id: int,
    document_type_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)

    existing = db.query(DocumentMeta).filter(
        DocumentMeta.episode_id == episode.id, DocumentMeta.document_type_id == document_type_id,
    ).first()

    # Replacing an already-uploaded document on an Active employee needs
    # approval - same HR_ADMIN/non-ACTIVE bypass as _save_or_request. The
    # new file is staged on disk but the old document stays live until
    # the change request is approved (approval_service.review_change_request).
    if existing and user.role.name != RoleName.HR_ADMIN and episode.status == EpisodeStatus.ACTIVE:
        staged = document_service.stage_replacement(db, episode, document_type_id, file)
        request = approval_service.create_document_change_request(db, episode, existing, staged, user)
        db.commit()
        return {"ok": True, "submitted_for_approval": True, "change_request_id": request.id}

    record = document_service.save_upload(db, episode, document_type_id, file, user)
    audit_service.record(db, "DOCUMENT", episode.id, AuditAction.CREATE, user, new_value=record.document_type)
    db.commit()
    db.refresh(record)
    return {"ok": True, "id": record.id, "file_name": record.file_name, "submitted_for_approval": False}


@router.get("/{episode_id}/documents/{document_id}/download", dependencies=[Depends(require_permission(Permission.EMPLOYEE_DOCUMENTS_VIEW))])
def download_document(episode_id: int, document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    document = db.query(DocumentMeta).filter(DocumentMeta.id == document_id, DocumentMeta.episode_id == episode.id).first()
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    path = document_service.resolve_file_path(document)
    return FileResponse(path, filename=document.file_name, media_type=document.mime_type)


@router.delete("/{episode_id}/documents/{document_id}", dependencies=[Depends(require_permission(Permission.EMPLOYEE_DOCUMENTS_UPLOAD))])
def delete_document(episode_id: int, document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    document = db.query(DocumentMeta).filter(DocumentMeta.id == document_id, DocumentMeta.episode_id == episode.id).first()
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    path = document_service.resolve_file_path(document)
    if os.path.exists(path):
        os.remove(path)
    db.delete(document)
    audit_service.record(db, "DOCUMENT", episode.id, AuditAction.UPDATE, user, old_value=f"removed document {document_id}")
    db.commit()
    return {"ok": True}


@router.post("/{episode_id}/dependents", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def add_dependent(episode_id: int, payload: DependentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    db.add(Dependent(episode_id=episode.id, **payload.model_dump()))
    audit_service.record(db, "DEPENDENT", episode.id, AuditAction.CREATE, user)
    db.commit()
    return {"ok": True}


@router.delete("/{episode_id}/dependents/{dependent_id}", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def delete_dependent(episode_id: int, dependent_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    dependent = db.query(Dependent).filter(Dependent.id == dependent_id, Dependent.episode_id == episode.id).first()
    if not dependent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dependent not found")
    db.delete(dependent)
    audit_service.record(db, "DEPENDENT", episode.id, AuditAction.UPDATE, user, old_value=f"removed dependent {dependent_id}")
    db.commit()
    return {"ok": True}


@router.post("/{episode_id}/nominees", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def add_nominee(episode_id: int, payload: NomineeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)

    if payload.percentage:
        current_total = employee_service.nominee_total(db, episode.id, payload.nomination_type)
        if current_total + payload.percentage > 100.01:
            type_label = payload.nomination_type or "unspecified type"
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Nominees for {type_label} already total {current_total:g}% - adding {payload.percentage:g}% would exceed 100%",
            )

    db.add(Nominee(episode_id=episode.id, **payload.model_dump()))
    audit_service.record(db, "NOMINEE", episode.id, AuditAction.CREATE, user)
    db.commit()
    return {"ok": True}


@router.delete("/{episode_id}/nominees/{nominee_id}", dependencies=[Depends(require_permission(Permission.EMPLOYEE_EDIT))])
def delete_nominee(episode_id: int, nominee_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    nominee = db.query(Nominee).filter(Nominee.id == nominee_id, Nominee.episode_id == episode.id).first()
    if not nominee:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nominee not found")
    db.delete(nominee)
    audit_service.record(db, "NOMINEE", episode.id, AuditAction.UPDATE, user, old_value=f"removed nominee {nominee_id}")
    db.commit()
    return {"ok": True}


def _transition(db: Session, episode: EmploymentEpisode, from_status: str, to_status: str, user: User):
    if episode.status != from_status:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Only {from_status} records can move to {to_status}")
    old_status = episode.status
    episode.status = to_status
    db.add(episode)
    audit_service.record(db, "EMPLOYMENT_EPISODE", episode.id, AuditAction.STATUS_CHANGE, user, old_value=old_status, new_value=to_status)
    db.commit()
    return {"ok": True, "status": episode.status}


@router.post("/{episode_id}/submit", dependencies=[Depends(require_permission(Permission.EMPLOYEE_CREATE))])
def submit_for_approval(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    return _transition(db, episode, EpisodeStatus.DRAFT, EpisodeStatus.PENDING_APPROVAL, user)


@router.post("/{episode_id}/approve")
def approve_employee(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    approval_service.authorize_approval(db, user, episode, TransactionType.EMPLOYEE_CREATION)
    return _transition(db, episode, EpisodeStatus.PENDING_APPROVAL, EpisodeStatus.ACTIVE, user)


@router.post("/{episode_id}/reject")
def reject_employee(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    approval_service.authorize_approval(db, user, episode, TransactionType.EMPLOYEE_CREATION)
    return _transition(db, episode, EpisodeStatus.PENDING_APPROVAL, EpisodeStatus.DRAFT, user)


def _separation_dict(episode: EmploymentEpisode) -> dict | None:
    r = episode.separation
    if not r:
        return None
    return {
        "id": r.id, "separation_type": r.separation_type, "resignation_date": r.resignation_date,
        "notice_period_days": r.notice_period_days, "last_working_date": r.last_working_date,
        "reason": r.reason, "remarks": r.remarks,
        "exit_interview_done": r.exit_interview_done, "asset_return_done": r.asset_return_done,
        "clearance_done": r.clearance_done, "document_issuance_done": r.document_issuance_done,
        "full_final_status": r.full_final_status,
    }


@router.post("/{episode_id}/separate", dependencies=[Depends(require_permission(Permission.EMPLOYEE_SEPARATE))])
def initiate_separation(episode_id: int, payload: SeparationIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Starts the exit flow (blueprint §16): captures the separation
    details and moves the employee to NOTICE_PERIOD, not straight to
    SEPARATED - the exit checklist (exit interview/asset return/clearance/
    document issuance) and Full & Final status are then worked through via
    the /separation/checklist endpoint before finalizing with
    /separation/complete. Re-postable while still in Notice Period to
    amend the details (e.g. Last Working Date changes)."""
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    if episode.status not in (EpisodeStatus.ACTIVE, EpisodeStatus.NOTICE_PERIOD):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only an Active employee (or one already in Notice Period) can have their exit initiated")

    record = db.query(SeparationRecord).filter(SeparationRecord.episode_id == episode.id).first()
    if not record:
        record = SeparationRecord(episode_id=episode.id)
        db.add(record)
    for field, value in payload.model_dump().items():
        setattr(record, field, value)

    old_status = episode.status
    episode.status = EpisodeStatus.NOTICE_PERIOD
    episode.separation_date = payload.last_working_date
    episode.separation_reason = payload.reason
    db.add(episode)
    audit_service.record(db, "SEPARATION", episode.id, AuditAction.STATUS_CHANGE, user, old_value=old_status, new_value=episode.status)
    db.commit()
    return {"ok": True, "status": episode.status}


@router.put("/{episode_id}/separation/checklist", dependencies=[Depends(require_permission(Permission.EMPLOYEE_SEPARATE))])
def update_separation_checklist(episode_id: int, payload: SeparationChecklistUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    record = db.query(SeparationRecord).filter(SeparationRecord.episode_id == episode.id).first()
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No exit has been initiated for this employee")
    for field, value in payload.model_dump().items():
        setattr(record, field, value)
    if payload.last_working_date:
        episode.separation_date = payload.last_working_date
        db.add(episode)
    audit_service.record(db, "SEPARATION", episode.id, AuditAction.UPDATE, user)
    db.commit()
    return {"ok": True}


@router.post("/{episode_id}/separation/complete", dependencies=[Depends(require_permission(Permission.EMPLOYEE_SEPARATE))])
def complete_separation(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    if episode.status != EpisodeStatus.NOTICE_PERIOD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only an employee in Notice Period can be marked Separated")
    old_status = episode.status
    episode.status = EpisodeStatus.SEPARATED
    db.add(episode)
    audit_service.record(db, "EMPLOYMENT_EPISODE", episode.id, AuditAction.STATUS_CHANGE, user, old_value=old_status, new_value=episode.status)
    db.commit()
    return {"ok": True, "status": episode.status}


@router.post("/{episode_id}/separation/cancel", dependencies=[Depends(require_permission(Permission.EMPLOYEE_SEPARATE))])
def cancel_separation(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Reverses an in-progress exit (employee changed their mind, or it
    was started in error) back to Active. The SeparationRecord is kept
    (not deleted) for audit history; re-initiating overwrites it."""
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    if episode.status != EpisodeStatus.NOTICE_PERIOD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only an employee in Notice Period can have their exit cancelled")
    old_status = episode.status
    episode.status = EpisodeStatus.ACTIVE
    episode.separation_date = None
    episode.separation_reason = None
    db.add(episode)
    audit_service.record(db, "EMPLOYMENT_EPISODE", episode.id, AuditAction.STATUS_CHANGE, user, old_value=old_status, new_value=episode.status)
    db.commit()
    return {"ok": True, "status": episode.status}


# ---------------------------------------------------------------------------
# Change requests (blueprint §15)
# ---------------------------------------------------------------------------

@router.get("-change-requests")
def list_change_requests(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(ChangeRequest).order_by(ChangeRequest.created_at.desc())
    if user.role.name != RoleName.HR_ADMIN and not permission_service.has_permission(db, user, Permission.CHANGE_REQUESTS_REVIEW):
        query = query.filter(ChangeRequest.requested_by_id == user.id)
    rows = query.all()
    return [
        {
            "id": r.id, "episode_id": r.episode_id, "transaction_type": r.transaction_type,
            "changes": json.loads(r.changes_json) if r.changes_json else {},
            "previous_values": json.loads(r.previous_values_json) if r.previous_values_json else {},
            "status": r.status, "requested_by": r.requested_by.username if r.requested_by else None,
            "reviewed_by": r.reviewed_by.username if r.reviewed_by else None,
            "review_remarks": r.review_remarks, "created_at": r.created_at,
        } for r in rows
    ]


@router.get("-change-requests/{request_id}/preview")
def preview_document_change(request_id: int, which: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Streams the old (pre-change) or new (staged) file for a
    DOCUMENT_CHANGE request, so a reviewer can compare both before
    approving - the staged file has no DocumentMeta row of its own yet."""
    request = db.query(ChangeRequest).filter(ChangeRequest.id == request_id).first()
    if not request or request.transaction_type != TransactionType.DOCUMENT_CHANGE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a document change request")
    if not (
        user.role.name == RoleName.HR_ADMIN
        or permission_service.has_permission(db, user, Permission.CHANGE_REQUESTS_REVIEW)
        or request.requested_by_id == user.id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to view this document")

    changes = json.loads(request.changes_json)
    previous = json.loads(request.previous_values_json)
    if which == "new":
        object_key, file_name = changes["new_object_key"], changes["new_file_name"]
    elif which == "old":
        object_key, file_name = previous["old_object_key"], previous["old_file_name"]
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "which must be 'old' or 'new'")

    path = os.path.join(settings.UPLOAD_DIR, object_key)
    if not os.path.exists(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return FileResponse(path, filename=file_name)


@router.post("-change-requests/{request_id}/approve")
def approve_change_request(request_id: int, payload: ChangeRequestReview, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    request = db.query(ChangeRequest).filter(ChangeRequest.id == request_id).first()
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change request not found")
    approval_service.review_change_request(db, request, user, approve=True, remarks=payload.remarks)
    db.commit()
    return {"ok": True}


@router.post("-change-requests/{request_id}/reject")
def reject_change_request(request_id: int, payload: ChangeRequestReview, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    request = db.query(ChangeRequest).filter(ChangeRequest.id == request_id).first()
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change request not found")
    approval_service.review_change_request(db, request, user, approve=False, remarks=payload.remarks)
    db.commit()
    return {"ok": True}


@router.get("-audit-logs", dependencies=[Depends(require_permission(Permission.AUDIT_VIEW))])
def list_all_audit_logs(db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(500).all()
    return [
        {
            "timestamp": l.timestamp, "username": l.username, "role": l.role, "action": l.action,
            "entity": l.entity, "record_id": l.record_id, "old_value": l.old_value, "new_value": l.new_value,
        } for l in logs
    ]


@router.get("/{episode_id}/audit", dependencies=[Depends(require_permission(Permission.EMPLOYEE_VIEW))])
def get_audit_trail(episode_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    episode = _get_episode(db, episode_id)
    _check_scope(db, user, episode)
    logs = db.query(AuditLog).filter(AuditLog.record_id == str(episode_id)).order_by(AuditLog.timestamp.desc()).all()
    return [
        {
            "timestamp": l.timestamp, "username": l.username, "role": l.role, "action": l.action,
            "entity": l.entity, "old_value": l.old_value, "new_value": l.new_value,
        } for l in logs
    ]
