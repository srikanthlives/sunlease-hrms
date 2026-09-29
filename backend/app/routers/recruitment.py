import io
import json
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_hr_admin, require_permission
from app.db.session import atomic_session, get_db
from app.models.enums import AuditAction, Permission, TransactionType
from app.models.models import (
    Candidate, CandidateChangeRequest, CandidateDocument, CandidateStageResult,
    DesignationCriteria, Project, SelectionCriteria, User,
)
from app.schemas.recruitment import (
    CandidateIn, CandidateStageResultIn, CandidateTransferIn, ChangeRequestReviewIn,
    ConvertCandidateIn, DesignationCriteriaIn, DesignationCriteriaUpdateIn, SelectionCriteriaIn,
)
from app.services import audit_service, candidate_bulk_import_service, document_service, employee_service, licence_service, permission_service, recruitment_service
from app.services.storage import get_storage

router = APIRouter(prefix="/api/v1/recruitment", tags=["recruitment"], dependencies=[Depends(get_current_user)])


# ---------------------------------------------------------------------------
# Selection Criteria (master) + Designation Criteria (assignment) - admin
# config, same gating convention as Document Configuration/Driving Licence
# Configuration (routers/masters.py): readable by any authenticated user
# (router-level get_current_user dependency is enough), but only HR_ADMIN/
# SUPER_ADMIN can create/edit/delete.
# ---------------------------------------------------------------------------

def _criteria_dict(c: SelectionCriteria) -> dict:
    return {"id": c.id, "name": c.name, "description": c.description, "is_active": c.is_active}


@router.get("/criteria")
def list_criteria(include_inactive: bool = False, db: Session = Depends(get_db)):
    query = db.query(SelectionCriteria)
    if not include_inactive:
        query = query.filter(SelectionCriteria.is_active.is_(True))
    return [_criteria_dict(c) for c in query.order_by(SelectionCriteria.name).all()]


@router.post("/criteria", dependencies=[Depends(require_hr_admin)])
def create_criteria(payload: SelectionCriteriaIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.query(SelectionCriteria).filter(SelectionCriteria.name == payload.name).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A selection criteria with this name already exists")
    c = SelectionCriteria(**payload.model_dump())
    db.add(c)
    db.flush()
    audit_service.record(db, "SELECTION_CRITERIA", c.id, AuditAction.CREATE, user)
    db.commit()
    return _criteria_dict(c)


@router.put("/criteria/{criteria_id}", dependencies=[Depends(require_hr_admin)])
def update_criteria(criteria_id: int, payload: SelectionCriteriaIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(SelectionCriteria).filter(SelectionCriteria.id == criteria_id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Selection criteria not found")
    for field, value in payload.model_dump().items():
        setattr(c, field, value)
    audit_service.record(db, "SELECTION_CRITERIA", c.id, AuditAction.UPDATE, user)
    db.commit()
    return _criteria_dict(c)


def _designation_criteria_dict(r: DesignationCriteria) -> dict:
    return {
        "id": r.id, "designation_id": r.designation_id, "designation_name": r.designation.name if r.designation else None,
        "cost_center_id": r.cost_center_id, "cost_center_name": r.cost_center.name if r.cost_center else None,
        "criteria_id": r.criteria_id, "criteria_name": r.criteria.name if r.criteria else None,
        "is_mandatory": r.is_mandatory, "sequence": r.sequence, "is_active": r.is_active,
    }


@router.get("/designation-criteria")
def list_designation_criteria(designation_id: int | None = None, include_inactive: bool = False, db: Session = Depends(get_db)):
    query = db.query(DesignationCriteria)
    if designation_id is not None:
        query = query.filter(DesignationCriteria.designation_id == designation_id)
    if not include_inactive:
        query = query.filter(DesignationCriteria.is_active.is_(True))
    rows = query.order_by(DesignationCriteria.designation_id, DesignationCriteria.sequence).all()
    return [_designation_criteria_dict(r) for r in rows]


@router.post("/designation-criteria", dependencies=[Depends(require_hr_admin)])
def create_designation_criteria(payload: DesignationCriteriaIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = (
        db.query(DesignationCriteria)
        .filter(
            DesignationCriteria.designation_id == payload.designation_id,
            DesignationCriteria.cost_center_id == payload.cost_center_id,
            DesignationCriteria.criteria_id == payload.criteria_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This criteria is already required for this designation/cost center")
    r = DesignationCriteria(**payload.model_dump())
    db.add(r)
    db.flush()
    audit_service.record(db, "DESIGNATION_CRITERIA", r.id, AuditAction.CREATE, user)
    db.commit()
    return _designation_criteria_dict(r)


@router.put("/designation-criteria/{row_id}", dependencies=[Depends(require_hr_admin)])
def update_designation_criteria(row_id: int, payload: DesignationCriteriaUpdateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Edits Mandatory/Optional, Sequence, and Active/Inactive on an
    existing requirement - deactivating one (rather than deleting it)
    stops it from being required for future candidates while keeping the
    row's history/audit trail intact, same "deactivate over delete"
    convention as every other master in this codebase."""
    r = db.query(DesignationCriteria).filter(DesignationCriteria.id == row_id).first()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    r.is_mandatory = payload.is_mandatory
    r.sequence = payload.sequence
    r.is_active = payload.is_active
    db.add(r)
    audit_service.record(db, "DESIGNATION_CRITERIA", r.id, AuditAction.UPDATE, user)
    db.commit()
    return _designation_criteria_dict(r)


@router.delete("/designation-criteria/{row_id}", dependencies=[Depends(require_hr_admin)])
def delete_designation_criteria(row_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Hard-deletes only if no candidate in this row's scope has ever
    been tested against it yet - a CandidateStageResult isn't linked to
    this row by FK (it's keyed by candidate_id+criteria_id directly, see
    CandidateStageResult's docstring), so recorded results would silently
    survive a delete, invisible from then on but not actually gone -
    surprising for HR. Once real test data exists, use Deactivate
    instead (keeps the row and its history, just stops it applying to
    new candidates)."""
    r = db.query(DesignationCriteria).filter(DesignationCriteria.id == row_id).first()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    candidates_query = db.query(Candidate).filter(Candidate.applied_designation_id == r.designation_id)
    if r.cost_center_id is not None:
        candidates_query = candidates_query.filter(Candidate.applied_cost_center_id == r.cost_center_id)
    candidate_ids = [c.id for c in candidates_query.all()]
    has_results = bool(candidate_ids) and db.query(CandidateStageResult).filter(
        CandidateStageResult.criteria_id == r.criteria_id,
        CandidateStageResult.candidate_id.in_(candidate_ids),
    ).first()
    if has_results:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This requirement already has recorded candidate test results - deactivate it instead of removing it.",
        )

    db.delete(r)
    audit_service.record(db, "DESIGNATION_CRITERIA", row_id, AuditAction.UPDATE, user, old_value="removed")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

def _candidate_summary_dict(c: Candidate) -> dict:
    return {
        "id": c.id, "reference_number": c.reference_number,
        "first_name": c.first_name, "last_name": c.last_name,
        "applied_designation_id": c.applied_designation_id, "designation_name": c.designation.name if c.designation else None,
        "applied_cost_center_id": c.applied_cost_center_id, "cost_center_name": c.cost_center.name if c.cost_center else None,
        "applied_project_id": c.applied_project_id, "applied_project_name": c.project.name if c.project else None,
        "applied_employee_category_id": c.applied_employee_category_id,
        "applied_employee_category_name": c.employee_category.name if c.employee_category else None,
        "applied_date": c.applied_date, "status": c.status,
        "mobile_number": c.mobile_number,
        # Extra list-view columns (hidden by default in the UI).
        "gender": c.gender, "date_of_birth": c.date_of_birth, "alternate_mobile_number": c.alternate_mobile_number,
        "personal_email": c.personal_email, "educational_qualification": c.educational_qualification,
        "total_experience_years": c.total_experience_years, "current_designation": c.current_designation,
        "current_company_name": c.current_company_name, "source": c.source, "remarks": c.remarks, "created_at": c.created_at,
    }


def _candidate_detail_dict(db: Session, c: Candidate, user: User | None = None) -> dict:
    return {
        **_candidate_summary_dict(c),
        "can_approve": recruitment_service.can_review(db, user, c) if user else False,
        "middle_name": c.middle_name, "father_husband_name": c.father_husband_name,
        "gender": c.gender, "date_of_birth": c.date_of_birth,
        "alternate_mobile_number": c.alternate_mobile_number, "personal_email": c.personal_email,
        "educational_qualification": c.educational_qualification,
        "current_designation": c.current_designation, "current_company_name": c.current_company_name,
        "current_company_details": c.current_company_details, "current_date_of_joining": c.current_date_of_joining,
        "total_experience_years": c.total_experience_years,
        "aadhaar": c.aadhaar, "aadhaar_name": c.aadhaar_name, "aadhaar_dob": c.aadhaar_dob,
        "pan": c.pan, "pan_name": c.pan_name, "pan_dob": c.pan_dob,
        "dl_licence_number": c.dl_licence_number, "dl_badge_number": c.dl_badge_number,
        "dl_vehicle_class": c.dl_vehicle_class, "dl_issuing_authority": c.dl_issuing_authority,
        "dl_issue_date": c.dl_issue_date, "dl_expiry_date": c.dl_expiry_date,
        "driving_licence_requirement": licence_service.resolve_driving_licence_requirement_for_candidate(db, c),
        "source": c.source, "remarks": c.remarks,
        "converted_employee_id": c.converted_employee_id, "converted_episode_id": c.converted_episode_id,
        "rejoin_employee_number": _rejoin_number(db, c),
        "criteria_status": recruitment_service.criteria_status(db, c),
        "all_mandatory_passed": recruitment_service.all_mandatory_passed(db, c),
        "aadhaar_duplicate_warning": recruitment_service.check_aadhaar_duplicates(db, c.aadhaar, exclude_candidate_id=c.id),
        "required_documents": document_service.resolve_required_documents_for_candidate(db, c),
    }


def _rejoin_number(db: Session, c: Candidate) -> str | None:
    """A requalified ex-employee coming back to a Cost Center they served
    before keeps their number there (None = a new number is entered)."""
    if not c.converted_employee_id or c.status == "CONVERTED":
        return None
    found = employee_service.number_for_cost_center(db, c.converted_employee_id, c.applied_cost_center_id)
    return found[0] if found else None


def _get_candidate(db: Session, candidate_id: int) -> Candidate:
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    return c


def _check_applied_scope(db: Session, user: User, cost_center_id: int | None, project_id: int | None) -> None:
    """Non-admin users can only create/edit candidates in Cost Centers (and
    Projects under them) they're scoped to - the dropdowns are already
    filtered (routers/masters.py), this is the server-side guard so the
    restriction can't be bypassed by calling the API directly."""
    allowed = permission_service.user_cost_center_ids(db, user)
    if allowed is None:
        return
    if cost_center_id is not None and cost_center_id not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this Cost Center")
    if project_id is not None:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project and project.cost_center_id not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this Project's Cost Center")


def _check_project_in_cost_center(db: Session, cost_center_id: int, project_id: int) -> None:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or project.cost_center_id != cost_center_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Project does not belong to the selected Cost Center")


@router.get("/candidates", dependencies=[Depends(require_permission(Permission.RECRUITMENT_VIEW))])
def list_candidates(status_: str | None = None, designation_id: int | None = None, cost_center_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Candidate)
    allowed = permission_service.user_cost_center_ids(db, user)
    if allowed is not None:
        query = query.filter(Candidate.applied_cost_center_id.in_(allowed))
    if status_:
        query = query.filter(Candidate.status == status_)
    if designation_id is not None:
        query = query.filter(Candidate.applied_designation_id == designation_id)
    if cost_center_id is not None:
        query = query.filter(Candidate.applied_cost_center_id == cost_center_id)
    rows = query.order_by(Candidate.created_at.desc()).all()
    out = []
    for c in rows:
        criteria = recruitment_service.criteria_status(db, c)
        out.append({
            **_candidate_summary_dict(c),
            # Counts for the list view's Documents/Tests button badges - the
            # full lists (which documents/tests, uploaded or not) are fetched
            # on demand from GET /candidates/{id} when a popup is opened,
            # rather than carried on every row here.
            "documents_uploaded_count": len(c.documents),
            "tests_recorded_count": sum(1 for r in criteria if r["result"] != "PENDING"),
            "tests_total_count": len(criteria),
        })
    return out


@router.get("/candidates-bulk-upload-template", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def download_candidates_bulk_upload_template(db: Session = Depends(get_db)):
    wb = candidate_bulk_import_service.build_template_workbook(db)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=hrms_candidate_bulk_upload_template.xlsx"},
    )


@router.post("/candidates-bulk-upload", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def bulk_upload_candidates(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    content = file.file.read()
    with atomic_session() as db:  # all-or-nothing: any bad row rolls the whole file back
        result = candidate_bulk_import_service.import_candidates_workbook(db, content, user)
        db.commit()
    return result


@router.post("/candidates", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def create_candidate(payload: CandidateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _check_applied_scope(db, user, payload.applied_cost_center_id, payload.applied_project_id)
    _check_project_in_cost_center(db, payload.applied_cost_center_id, payload.applied_project_id)
    recruitment_service.validate_unique_identifiers(db, payload.aadhaar, payload.pan, payload.dl_licence_number)
    candidate = Candidate(**payload.model_dump())
    db.add(candidate)
    db.flush()
    candidate.reference_number = recruitment_service.generate_reference_number(db, candidate)
    db.add(candidate)
    audit_service.record(db, "CANDIDATE", candidate.id, AuditAction.CREATE, user, new_value=candidate.reference_number)
    db.commit()
    db.refresh(candidate)
    return _candidate_detail_dict(db, candidate)


@router.get("/candidates/{candidate_id}", dependencies=[Depends(require_permission(Permission.RECRUITMENT_VIEW))])
def get_candidate(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _candidate_detail_dict(db, _get_candidate(db, candidate_id), user)


@router.put("/candidates/{candidate_id}", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def update_candidate(candidate_id: int, payload: CandidateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Direct-applies while the candidate is Applied/Pending Approval/
    Rejected; once APPROVED, queues a CandidateChangeRequest instead (see
    recruitment_service.save_or_request_candidate_update) - only fields
    that actually changed are included, so a resubmitted form with
    untouched fields doesn't manufacture a change request out of nothing."""
    candidate = _get_candidate(db, candidate_id)
    if candidate.status == "CONVERTED":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This candidate has already been converted to an employee")
    _check_applied_scope(db, user, candidate.applied_cost_center_id, None)
    _check_applied_scope(db, user, payload.applied_cost_center_id, payload.applied_project_id)
    recruitment_service.validate_unique_identifiers(
        db, payload.aadhaar, payload.pan, payload.dl_licence_number,
        exclude_candidate_id=candidate.id, exclude_employee_id=candidate.converted_employee_id,
    )
    changes = {
        field: value for field, value in payload.model_dump().items()
        if getattr(candidate, field) != value
    }
    result = recruitment_service.save_or_request_candidate_update(db, candidate, changes, user)
    db.commit()
    db.refresh(candidate)
    return {**_candidate_detail_dict(db, candidate), **result}


@router.post("/candidates/{candidate_id}/disqualify", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def disqualify_candidate(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Terminal rejection - this candidate is out of consideration
    entirely (distinct from /reject below, which just sends a
    Pending-Approval submission back to Applied for correction)."""
    candidate = _get_candidate(db, candidate_id)
    recruitment_service.disqualify_candidate(db, candidate, user)
    db.commit()
    return {"ok": True}


@router.post("/candidates/{candidate_id}/requalify", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def requalify_candidate(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Reopens a Rejected or Converted candidate back to Applied so they
    can be reconsidered through the whole pipeline again - covers both
    "we want to give this disqualified candidate another look" and a
    Converted-and-since-resigned person reapplying."""
    candidate = _get_candidate(db, candidate_id)
    recruitment_service.requalify_candidate(db, candidate, user)
    db.commit()
    return {"ok": True, "status": candidate.status}


@router.post("/candidates/{candidate_id}/transfer", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def transfer_candidate(candidate_id: int, payload: CandidateTransferIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Moves a candidate to another Cost Center/Project; reference_number is
    never regenerated. Needs access to BOTH the current and the destination
    Cost Center (admins have all). Same approval behaviour as any edit: an
    APPROVED candidate's move is queued as a change request."""
    candidate = _get_candidate(db, candidate_id)
    if candidate.status in ("CONVERTED", "REJECTED"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"A {candidate.status} candidate cannot be transferred")
    _check_applied_scope(db, user, candidate.applied_cost_center_id, candidate.applied_project_id)
    _check_applied_scope(db, user, payload.applied_cost_center_id, payload.applied_project_id)
    _check_project_in_cost_center(db, payload.applied_cost_center_id, payload.applied_project_id)
    if candidate.applied_cost_center_id == payload.applied_cost_center_id and candidate.applied_project_id == payload.applied_project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Candidate is already in this Cost Center and Project")
    old = f"cost_center={candidate.applied_cost_center_id}, project={candidate.applied_project_id}"
    result = recruitment_service.save_or_request_candidate_update(
        db, candidate, {"applied_cost_center_id": payload.applied_cost_center_id, "applied_project_id": payload.applied_project_id}, user,
    )
    verb = "transfer requested" if result["submitted_for_approval"] else "transferred"
    audit_service.record(
        db, "CANDIDATE", candidate.id, AuditAction.UPDATE, user, old_value=old,
        new_value=f"{verb} to cost_center={payload.applied_cost_center_id}, project={payload.applied_project_id}"
                  f" (reference {candidate.reference_number} unchanged)" + (f" - {payload.remarks}" if payload.remarks else ""),
    )
    db.commit()
    db.refresh(candidate)
    return {**_candidate_detail_dict(db, candidate), **result}


@router.post("/candidates/{candidate_id}/submit", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def submit_candidate(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    candidate = _get_candidate(db, candidate_id)
    recruitment_service.submit_candidate(db, candidate, user)
    db.commit()
    return {"ok": True, "status": candidate.status}


@router.post("/candidates/{candidate_id}/approve")
def approve_candidate_submission(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Grants the initial approval a candidate needs before Selection
    Criteria can be recorded - routed through the same ApprovalRule
    engine as Employee creation (no permission dependency here, same as
    employees.py's own /approve: authorization is entirely inside
    recruitment_service.approve_candidate_submission)."""
    candidate = _get_candidate(db, candidate_id)
    recruitment_service.approve_candidate_submission(db, candidate, user)
    db.commit()
    return {"ok": True, "status": candidate.status}


@router.post("/candidates/{candidate_id}/reject")
def reject_candidate_submission(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    candidate = _get_candidate(db, candidate_id)
    recruitment_service.return_candidate_for_correction(db, candidate, user)
    db.commit()
    return {"ok": True, "status": candidate.status}


@router.delete("/candidates/{candidate_id}", dependencies=[Depends(require_hr_admin)])
def delete_candidate(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """HR Admin / Super Admin only, and only for a candidate still in
    Applied - nothing has been submitted or approved yet, so there's
    nothing to lose. Anyone further along should be Disqualified instead
    (keeps the record). Removes everything attached to the candidate:
    documents and their files, test results and their proof files, and
    any change requests."""
    candidate = _get_candidate(db, candidate_id)
    if candidate.status != "APPLIED":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only an Applied candidate can be deleted - use Disqualify for one that has progressed")
    for doc in list(candidate.documents):
        document_service.delete_candidate_document(db, doc)
    for result in list(candidate.stage_results):
        if result.attachment_object_key:
            get_storage().delete(result.attachment_object_key)
    db.query(CandidateChangeRequest).filter(CandidateChangeRequest.candidate_id == candidate.id).delete(synchronize_session=False)
    reference = candidate.reference_number
    db.delete(candidate)  # stage results cascade with the candidate
    audit_service.record(db, "CANDIDATE", candidate_id, AuditAction.UPDATE, user, old_value=f"deleted {reference}")
    db.commit()
    return {"ok": True}


@router.post("/candidates/{candidate_id}/stage-results", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def record_stage_result(candidate_id: int, payload: CandidateStageResultIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    candidate = _get_candidate(db, candidate_id)
    recruitment_service.record_stage_result(db, candidate, payload.criteria_id, payload.result, payload.tested_on, payload.remarks, user)
    db.commit()
    return _candidate_detail_dict(db, candidate)


@router.post("/candidates/{candidate_id}/stage-results/{criteria_id}/attachment", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def upload_stage_result_attachment(
    candidate_id: int, criteria_id: int, file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Proof-of-completion for one selection criteria (e.g. a scanned test
    result/certificate) - independent of the PASS/FAIL result itself, so
    it can be uploaded before, alongside, or after the result is marked."""
    candidate = _get_candidate(db, candidate_id)
    if candidate.status == "CONVERTED":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This candidate has already been converted to an employee")
    stage_result = recruitment_service.get_or_create_stage_result(db, candidate, criteria_id)
    recruitment_service.save_stage_result_attachment(db, stage_result, file, user)
    db.commit()
    return {"ok": True, "attachment_file_name": stage_result.attachment_file_name}


def _get_stage_result_with_attachment(db: Session, candidate: Candidate, criteria_id: int) -> CandidateStageResult:
    stage_result = (
        db.query(CandidateStageResult)
        .filter(CandidateStageResult.candidate_id == candidate.id, CandidateStageResult.criteria_id == criteria_id)
        .first()
    )
    if not stage_result or not stage_result.attachment_object_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No proof document uploaded for this criteria")
    return stage_result


@router.get("/candidates/{candidate_id}/stage-results/{criteria_id}/attachment", dependencies=[Depends(require_permission(Permission.RECRUITMENT_VIEW))])
def download_stage_result_attachment(candidate_id: int, criteria_id: int, db: Session = Depends(get_db)):
    candidate = _get_candidate(db, candidate_id)
    stage_result = _get_stage_result_with_attachment(db, candidate, criteria_id)
    return document_service.serve_object(stage_result.attachment_object_key, media_type=stage_result.attachment_mime_type, download_name=stage_result.attachment_file_name)


@router.get("/candidates/{candidate_id}/stage-results/{criteria_id}/attachment/preview", dependencies=[Depends(require_permission(Permission.RECRUITMENT_VIEW))])
def preview_stage_result_attachment(candidate_id: int, criteria_id: int, db: Session = Depends(get_db)):
    candidate = _get_candidate(db, candidate_id)
    stage_result = _get_stage_result_with_attachment(db, candidate, criteria_id)
    return document_service.serve_object(stage_result.attachment_object_key, media_type=stage_result.attachment_mime_type)


@router.delete("/candidates/{candidate_id}/stage-results/{criteria_id}/attachment", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def delete_stage_result_attachment(candidate_id: int, criteria_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    candidate = _get_candidate(db, candidate_id)
    stage_result = _get_stage_result_with_attachment(db, candidate, criteria_id)
    recruitment_service.delete_stage_result_attachment(db, stage_result, user)
    db.commit()
    return {"ok": True}


@router.post("/candidates/{candidate_id}/convert", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def convert_candidate(candidate_id: int, payload: ConvertCandidateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    candidate = _get_candidate(db, candidate_id)
    episode = recruitment_service.convert_to_employee(
        db, candidate, payload.employee_number, payload.date_of_joining,
        payload.employment_type_id, payload.employee_category_id, payload.work_location_id,
        payload.confirmation_date, user,
    )
    db.commit()
    return {"ok": True, "episode_id": episode.id, "employee_id": episode.employee_id}


# ---------------------------------------------------------------------------
# Candidate documents - required set is NOT configured separately for
# recruitment; it reuses the same DocumentRequirement rules (scoped by
# Employee Category/Designation) already configured for employees on the
# Document Configuration admin screen, matched against the candidate's
# applied Category/Designation (document_service.resolve_required_documents_for_candidate).
# ---------------------------------------------------------------------------

def _get_candidate_document(db: Session, candidate: Candidate, document_id: int) -> CandidateDocument:
    doc = db.query(CandidateDocument).filter(CandidateDocument.id == document_id, CandidateDocument.candidate_id == candidate.id).first()
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.get("/candidates/{candidate_id}/documents/required", dependencies=[Depends(require_permission(Permission.RECRUITMENT_VIEW))])
def list_required_documents(candidate_id: int, db: Session = Depends(get_db)):
    return document_service.resolve_required_documents_for_candidate(db, _get_candidate(db, candidate_id))


@router.post("/candidates/{candidate_id}/documents", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def upload_candidate_document(
    candidate_id: int, document_type_id: int = Form(...), file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    candidate = _get_candidate(db, candidate_id)
    if candidate.status == "CONVERTED":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This candidate has already been converted to an employee")
    doc = document_service.save_candidate_document(db, candidate, document_type_id, file, user)
    audit_service.record(db, "CANDIDATE_DOCUMENT", candidate.id, AuditAction.UPDATE, user, new_value=doc.document_type)
    db.commit()
    return {"ok": True, "id": doc.id, "file_name": doc.file_name}


@router.get("/candidates/{candidate_id}/documents/{document_id}/preview", dependencies=[Depends(require_permission(Permission.RECRUITMENT_VIEW))])
def preview_candidate_document(candidate_id: int, document_id: int, db: Session = Depends(get_db)):
    candidate = _get_candidate(db, candidate_id)
    doc = _get_candidate_document(db, candidate, document_id)
    return document_service.serve_object(doc.object_key, media_type=doc.mime_type)


@router.get("/candidates/{candidate_id}/documents/{document_id}/download", dependencies=[Depends(require_permission(Permission.RECRUITMENT_VIEW))])
def download_candidate_document(candidate_id: int, document_id: int, db: Session = Depends(get_db)):
    candidate = _get_candidate(db, candidate_id)
    doc = _get_candidate_document(db, candidate, document_id)
    return document_service.serve_object(doc.object_key, media_type=doc.mime_type, download_name=doc.file_name)


@router.delete("/candidates/{candidate_id}/documents/{document_id}", dependencies=[Depends(require_permission(Permission.RECRUITMENT_MANAGE))])
def delete_candidate_document(candidate_id: int, document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Deletes the file from disk as well as the DB row - "clean the
    repository of deleted documents" (document_service.delete_candidate_document)
    - unless the candidate is already APPROVED, in which case the
    deletion is queued as a CandidateChangeRequest instead and only takes
    effect once an approver reviews it."""
    candidate = _get_candidate(db, candidate_id)
    if candidate.status == "CONVERTED":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This candidate has already been converted to an employee")
    doc = _get_candidate_document(db, candidate, document_id)

    if candidate.status == "APPROVED":
        recruitment_service.create_candidate_change_request(db, candidate, "DOCUMENT_DELETE", {"document_id": doc.id, "document_type": doc.document_type}, user)
        db.commit()
        return {"ok": True, "submitted_for_approval": True}

    document_service.delete_candidate_document(db, doc)
    audit_service.record(db, "CANDIDATE_DOCUMENT", candidate.id, AuditAction.UPDATE, user, old_value=f"removed {doc.document_type}")
    db.commit()
    return {"ok": True, "submitted_for_approval": False}


# ---------------------------------------------------------------------------
# Candidate change requests - edits/document-deletions queued while a
# candidate is APPROVED (recruitment_service.save_or_request_candidate_update,
# .create_candidate_change_request). Review authorization is the same
# ApprovalRule routing as the initial candidate approval, via
# recruitment_service.review_candidate_change_request.
# ---------------------------------------------------------------------------

def _change_request_dict(r: CandidateChangeRequest) -> dict:
    return {
        "id": r.id, "candidate_id": r.candidate_id,
        "candidate_reference_number": r.candidate.reference_number if r.candidate else None,
        "candidate_name": f"{r.candidate.first_name} {r.candidate.last_name}" if r.candidate else None,
        "request_type": r.request_type,
        "changes": json.loads(r.changes_json) if r.changes_json else {},
        "previous_values": json.loads(r.previous_values_json) if r.previous_values_json else {},
        "requested_by": r.requested_by.username if r.requested_by else None,
        "reviewed_by": r.reviewed_by.username if r.reviewed_by else None,
        "reviewed_at": r.reviewed_at,
        "review_remarks": r.review_remarks,
        "status": r.status,
        "created_at": r.created_at,
    }


@router.get("/candidates-change-requests", dependencies=[Depends(require_permission(Permission.RECRUITMENT_VIEW))])
def list_candidate_change_requests(status_: str | None = Query("PENDING"), candidate_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(CandidateChangeRequest)
    if status_:
        query = query.filter(CandidateChangeRequest.status == status_)
    if candidate_id is not None:
        query = query.filter(CandidateChangeRequest.candidate_id == candidate_id)
    rows = query.order_by(CandidateChangeRequest.created_at.desc()).all()
    candidates = {c.id: c for c in db.query(Candidate).filter(Candidate.id.in_({r.candidate_id for r in rows})).all()} if rows else {}
    return [
        {**_change_request_dict(r), "can_review": bool(candidates.get(r.candidate_id)) and recruitment_service.can_review(db, user, candidates[r.candidate_id], TransactionType.RECRUITMENT_CHANGE)}
        for r in rows
    ]


@router.post("/candidates-change-requests/{request_id}/approve")
def approve_candidate_change_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    request = db.query(CandidateChangeRequest).filter(CandidateChangeRequest.id == request_id).first()
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change request not found")
    recruitment_service.review_candidate_change_request(db, request, user, approve=True)
    db.commit()
    return {"ok": True}


@router.post("/candidates-change-requests/{request_id}/reject")
def reject_candidate_change_request(request_id: int, payload: ChangeRequestReviewIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    request = db.query(CandidateChangeRequest).filter(CandidateChangeRequest.id == request_id).first()
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change request not found")
    recruitment_service.review_candidate_change_request(db, request, user, approve=False, remarks=payload.remarks)
    db.commit()
    return {"ok": True}
