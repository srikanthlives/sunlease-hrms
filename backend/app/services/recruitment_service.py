import datetime as dt
import json
import os
import re

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import AuditAction, CandidateStatus, RoleName, TransactionType
from app.models.models import (
    Candidate, CandidateChangeRequest, CandidateDocument, CandidateSalaryComponent, CandidateStageResult,
    DesignationCriteria, DrivingLicenceDetail, Employee, EmploymentEpisode, SelectionCriteria, User,
)
from app.services import approval_service, audit_service, document_service, employee_service, payroll_service


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip()).strip("-").lower()
    return value or "file"


def generate_reference_number(db: Session, candidate: Candidate) -> str:
    """Company code / Cost Center code / Project code / sequence-within-
    that-scope, e.g. "SUNLEASE/CC-PDY/PRJ-01/003". The Project segment is
    omitted when the candidate has no applied_project_id (sequence then
    counts within Company+Cost Center only). Falls back to "NA" for a
    missing Company/Cost Center code (legacy rows created before those
    columns were required) rather than raising - a reference number
    should never block candidate creation."""
    cost_center = candidate.cost_center
    company = cost_center.company if cost_center else None
    company_code = (company.code if company else None) or "NA"
    cost_center_code = (cost_center.code if cost_center else None) or "NA"
    project_code = candidate.project.code if candidate.project else None

    scope_query = db.query(Candidate).filter(
        Candidate.applied_cost_center_id == candidate.applied_cost_center_id,
        Candidate.applied_project_id == candidate.applied_project_id,
        Candidate.id != candidate.id,
    )
    sequence = scope_query.count() + 1

    parts = [company_code, cost_center_code]
    if project_code:
        parts.append(project_code)
    parts.append(f"{sequence:03d}")
    return "/".join(parts)


def required_criteria(db: Session, designation_id: int, cost_center_id: int | None) -> list[DesignationCriteria]:
    """Most-specific-first: a Cost-Center-scoped requirement for this
    Designation overrides a global (cost_center_id IS NULL) requirement
    for the same SelectionCriteria - same cascade idea as
    LeaveEligibilityRule/ApprovalRule. Both scopes' *distinct* criteria
    still apply; only a duplicate criteria_id present in both prefers the
    more specific row."""
    rows = (
        db.query(DesignationCriteria)
        .filter(DesignationCriteria.designation_id == designation_id)
        .filter((DesignationCriteria.cost_center_id.is_(None)) | (DesignationCriteria.cost_center_id == cost_center_id))
        .all()
    )
    by_criteria: dict[int, DesignationCriteria] = {}
    for row in rows:
        existing = by_criteria.get(row.criteria_id)
        if existing is None or (existing.cost_center_id is None and row.cost_center_id is not None):
            by_criteria[row.criteria_id] = row
    return sorted(by_criteria.values(), key=lambda r: (r.sequence, r.id))


def criteria_status(db: Session, candidate: Candidate) -> list[dict]:
    required = required_criteria(db, candidate.applied_designation_id, candidate.applied_cost_center_id)
    results_by_criteria = {
        r.criteria_id: r for r in
        db.query(CandidateStageResult).filter(CandidateStageResult.candidate_id == candidate.id).all()
    }
    out = []
    for req in required:
        result = results_by_criteria.get(req.criteria_id)
        out.append({
            "criteria_id": req.criteria_id,
            "criteria_name": req.criteria.name if req.criteria else None,
            "is_mandatory": req.is_mandatory,
            "sequence": req.sequence,
            "result": result.result if result else "PENDING",
            "tested_on": result.tested_on if result else None,
            "remarks": result.remarks if result else None,
            "stage_result_id": result.id if result else None,
            "attachment_file_name": result.attachment_file_name if result else None,
        })
    return out


def check_aadhaar_duplicates(db: Session, aadhaar: str | None, exclude_candidate_id: int | None = None) -> list[str]:
    """Returns human-readable descriptions of any existing Employee or
    other Candidate already carrying this Aadhaar number - informational
    only (used to annotate the candidate detail response), the actual
    gate is validate_unique_identifiers below, called on create/update."""
    if not aadhaar:
        return []
    matches = []
    for emp in db.query(Employee).filter(Employee.aadhaar == aadhaar).all():
        matches.append(f"Employee: {emp.first_name} {emp.last_name}")
    query = db.query(Candidate).filter(Candidate.aadhaar == aadhaar)
    if exclude_candidate_id:
        query = query.filter(Candidate.id != exclude_candidate_id)
    for cand in query.all():
        matches.append(f"Candidate: {cand.first_name} {cand.last_name} ({cand.reference_number}, {cand.status})")
    return matches


def _find_matches(db: Session, employee_query, candidate_query, exclude_candidate_id: int | None) -> list[str]:
    matches = [f"Employee: {emp.first_name} {emp.last_name}" for emp in employee_query.all()]
    if exclude_candidate_id:
        candidate_query = candidate_query.filter(Candidate.id != exclude_candidate_id)
    matches += [f"Candidate: {c.first_name} {c.last_name} ({c.reference_number}, {c.status})" for c in candidate_query.all()]
    return matches


def validate_unique_identifiers(
    db: Session, aadhaar: str | None, pan: str | None, dl_licence_number: str | None,
    exclude_candidate_id: int | None = None,
) -> None:
    """Hard-blocks creating/updating a candidate whose Aadhaar, PAN, or
    Driving Licence Number matches an existing Employee or another
    Candidate - unlike the informational aadhaar_duplicate_warning this
    replaces, these three are treated as unique identifiers that can
    never legitimately collide between two different people, so there's
    nothing for HR to "judge" the way there might be for a name/mobile
    match; the row is simply rejected."""
    errors = []

    if aadhaar:
        matches = _find_matches(
            db, db.query(Employee).filter(Employee.aadhaar == aadhaar),
            db.query(Candidate).filter(Candidate.aadhaar == aadhaar), exclude_candidate_id,
        )
        if matches:
            errors.append(f"Aadhaar Number already used by {matches[0]}")

    if pan:
        matches = _find_matches(
            db, db.query(Employee).filter(Employee.pan == pan),
            db.query(Candidate).filter(Candidate.pan == pan), exclude_candidate_id,
        )
        if matches:
            errors.append(f"PAN Number already used by {matches[0]}")

    if dl_licence_number:
        employee_matches = [
            f"Employee: {r.episode.employee.first_name} {r.episode.employee.last_name}"
            for r in db.query(DrivingLicenceDetail).filter(DrivingLicenceDetail.licence_number == dl_licence_number).all()
            if r.episode and r.episode.employee
        ]
        candidate_query = db.query(Candidate).filter(Candidate.dl_licence_number == dl_licence_number)
        if exclude_candidate_id:
            candidate_query = candidate_query.filter(Candidate.id != exclude_candidate_id)
        candidate_matches = [f"Candidate: {c.first_name} {c.last_name} ({c.reference_number}, {c.status})" for c in candidate_query.all()]
        matches = employee_matches + candidate_matches
        if matches:
            errors.append(f"Driving Licence Number already used by {matches[0]}")

    if errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "; ".join(errors))


def authorize_candidate_approval(db: Session, user: User, candidate: Candidate, transaction_type: str = TransactionType.RECRUITMENT_APPROVAL) -> None:
    """Same routing/fallback logic as approval_service.authorize_approval,
    reimplemented standalone because that function takes an
    EmploymentEpisode (for its Cost Center lookup via OrgAssignment) and a
    Candidate has no episode - it already carries its own
    applied_cost_center_id/applied_employee_category_id directly, so
    approval_service.find_approval_rule (which only needs those two ids,
    not an episode) is reused as-is."""
    if user.role.name in (RoleName.HR_ADMIN, RoleName.SUPER_ADMIN):
        return
    rule = approval_service.find_approval_rule(db, transaction_type, candidate.applied_cost_center_id, candidate.applied_employee_category_id)
    if rule:
        if rule.approver_user_id is not None:
            if user.id != rule.approver_user_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the assigned approver for this record")
            return
        if user.role.name != rule.approver_role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role {rule.approver_role} to approve this record")
        return
    if user.role.name != RoleName.APPROVER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires the Approver role (no approval rule matched)")


def submit_candidate(db: Session, candidate: Candidate, user: User) -> None:
    if candidate.status != CandidateStatus.APPLIED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only an Applied candidate can be submitted for approval")
    candidate.status = CandidateStatus.PENDING_APPROVAL
    db.add(candidate)
    audit_service.record(db, "CANDIDATE", candidate.id, AuditAction.STATUS_CHANGE, user, new_value="PENDING_APPROVAL")


def approve_candidate_submission(db: Session, candidate: Candidate, user: User) -> None:
    if candidate.status != CandidateStatus.PENDING_APPROVAL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a candidate Pending Approval can be approved")
    authorize_candidate_approval(db, user, candidate)
    candidate.status = CandidateStatus.APPROVED
    db.add(candidate)
    audit_service.record(db, "CANDIDATE", candidate.id, AuditAction.STATUS_CHANGE, user, new_value="APPROVED")


def return_candidate_for_correction(db: Session, candidate: Candidate, user: User) -> None:
    """Sends a Pending-Approval candidate back to Applied so HR can fix
    something before resubmitting - mirrors EmploymentEpisode's own
    /reject (PENDING_APPROVAL -> DRAFT), distinct from disqualify_candidate
    below, which is a terminal rejection of the candidate entirely."""
    if candidate.status != CandidateStatus.PENDING_APPROVAL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a candidate Pending Approval can be returned for correction")
    authorize_candidate_approval(db, user, candidate)
    candidate.status = CandidateStatus.APPLIED
    db.add(candidate)
    audit_service.record(db, "CANDIDATE", candidate.id, AuditAction.STATUS_CHANGE, user, new_value="APPLIED (returned for correction)")


def disqualify_candidate(db: Session, candidate: Candidate, user: User) -> None:
    if candidate.status in (CandidateStatus.CONVERTED, CandidateStatus.REJECTED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"This candidate is already {candidate.status}")
    candidate.status = CandidateStatus.REJECTED
    db.add(candidate)
    audit_service.record(db, "CANDIDATE", candidate.id, AuditAction.STATUS_CHANGE, user, new_value="REJECTED")


def save_or_request_candidate_update(db: Session, candidate: Candidate, changes: dict, user: User) -> dict:
    """Direct-apply unless the candidate is already APPROVED, in which
    case the edit is queued as a CandidateChangeRequest instead - "approved
    data must not be overwritten directly" (blueprint §15), same principle
    as an ACTIVE EmploymentEpisode. `changes` should already be filtered
    to only the fields that actually differ from the current row."""
    if candidate.status == CandidateStatus.APPROVED:
        create_candidate_change_request(db, candidate, "FIELD_CHANGE", changes, user)
        return {"submitted_for_approval": True}
    for field, value in changes.items():
        setattr(candidate, field, value)
    db.add(candidate)
    audit_service.record(db, "CANDIDATE", candidate.id, AuditAction.UPDATE, user)
    return {"submitted_for_approval": False}


def create_candidate_change_request(db: Session, candidate: Candidate, request_type: str, changes: dict, user: User) -> CandidateChangeRequest:
    previous_values = {f: getattr(candidate, f) for f in changes} if request_type == "FIELD_CHANGE" else {}
    request = CandidateChangeRequest(
        candidate_id=candidate.id, request_type=request_type,
        changes_json=json.dumps(changes, default=str),
        previous_values_json=json.dumps(previous_values, default=str),
        requested_by_id=user.id, status="PENDING",
    )
    db.add(request)
    db.flush()
    audit_service.record(db, "CANDIDATE_CHANGE_REQUEST", request.id, AuditAction.CREATE, user, new_value=request_type)
    return request


def review_candidate_change_request(db: Session, request: CandidateChangeRequest, user: User, approve: bool, remarks: str | None = None) -> CandidateChangeRequest:
    if request.status != "PENDING":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This change request has already been reviewed")
    candidate = request.candidate
    authorize_candidate_approval(db, user, candidate, TransactionType.RECRUITMENT_CHANGE)

    request.reviewed_by_id = user.id
    request.reviewed_at = dt.datetime.utcnow()
    request.review_remarks = remarks

    if approve:
        changes = json.loads(request.changes_json)
        if request.request_type == "FIELD_CHANGE":
            for field, value in changes.items():
                setattr(candidate, field, value)
            db.add(candidate)
        elif request.request_type == "DOCUMENT_DELETE":
            doc = db.query(CandidateDocument).filter(CandidateDocument.id == changes["document_id"]).first()
            if doc:
                document_service.delete_candidate_document(db, doc)
        request.status = "APPROVED"
        audit_service.record(db, "CANDIDATE_CHANGE_REQUEST", request.id, AuditAction.APPROVE, user, new_value=request.changes_json)
    else:
        request.status = "REJECTED"
        audit_service.record(db, "CANDIDATE_CHANGE_REQUEST", request.id, AuditAction.REJECT, user, new_value=remarks)

    db.add(request)
    return request


def all_mandatory_passed(db: Session, candidate: Candidate) -> bool:
    statuses = criteria_status(db, candidate)
    mandatory = [s for s in statuses if s["is_mandatory"]]
    return len(mandatory) > 0 and all(s["result"] == "PASS" for s in mandatory)


def get_or_create_stage_result(db: Session, candidate: Candidate, criteria_id: int) -> CandidateStageResult:
    """Fetches this candidate's row for a criteria, creating a PENDING one
    if HR hasn't recorded a result yet - lets a proof document be attached
    (save_stage_result_attachment) independently of / before the result
    itself is marked, e.g. uploading the test certificate first and
    marking PASS/FAIL afterward."""
    if candidate.status != CandidateStatus.APPROVED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Candidate must be approved before Selection Criteria can be recorded")
    if not db.query(SelectionCriteria).filter(SelectionCriteria.id == criteria_id).first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Selection criteria not found")
    row = (
        db.query(CandidateStageResult)
        .filter(CandidateStageResult.candidate_id == candidate.id, CandidateStageResult.criteria_id == criteria_id)
        .first()
    )
    if not row:
        row = CandidateStageResult(candidate_id=candidate.id, criteria_id=criteria_id)
        db.add(row)
        db.flush()
    return row


def save_stage_result_attachment(db: Session, stage_result: CandidateStageResult, upload_file: UploadFile, actor: User) -> CandidateStageResult:
    """Proof-of-completion document for a selection criteria (e.g. a
    scanned test result/certificate) - one file per (candidate, criteria),
    replacing any prior upload, same local-disk convention as
    leave_service.save_attachment."""
    candidate = stage_result.candidate
    ext = os.path.splitext(upload_file.filename or "")[1]
    target_dir = os.path.join(document_service._candidate_upload_dir(candidate), "criteria-proofs")
    os.makedirs(target_dir, exist_ok=True)
    stored_name = f"{stage_result.criteria_id}-{_slug(os.path.splitext(upload_file.filename or '')[0])}{ext}"
    full_path = os.path.join(target_dir, stored_name)

    content = upload_file.file.read()
    with open(full_path, "wb") as f:
        f.write(content)

    stage_result.attachment_object_key = os.path.relpath(full_path, settings.UPLOAD_DIR)
    stage_result.attachment_file_name = upload_file.filename
    db.add(stage_result)
    audit_service.record(db, "CANDIDATE_STAGE_RESULT", stage_result.id, AuditAction.UPDATE, actor, new_value=f"attachment uploaded for criteria {stage_result.criteria_id}")
    return stage_result


def stage_result_attachment_path(stage_result: CandidateStageResult) -> str:
    return os.path.join(settings.UPLOAD_DIR, stage_result.attachment_object_key)


def record_stage_result(db: Session, candidate: Candidate, criteria_id: int, result: str, tested_on, remarks: str | None, user: User) -> CandidateStageResult:
    if candidate.status != CandidateStatus.APPROVED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Candidate must be approved before Selection Criteria can be recorded")
    criteria = db.query(SelectionCriteria).filter(SelectionCriteria.id == criteria_id).first()
    if not criteria:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Selection criteria not found")

    row = (
        db.query(CandidateStageResult)
        .filter(CandidateStageResult.candidate_id == candidate.id, CandidateStageResult.criteria_id == criteria_id)
        .first()
    )
    if not row:
        row = CandidateStageResult(candidate_id=candidate.id, criteria_id=criteria_id)
    row.result = result
    row.tested_on = tested_on
    row.remarks = remarks
    row.reviewed_by_id = user.id
    db.add(row)
    audit_service.record(db, "CANDIDATE_STAGE_RESULT", candidate.id, AuditAction.UPDATE, user, new_value=f"{criteria.name}={result}")
    return row


def convert_to_employee(
    db: Session, candidate: Candidate, employee_number: str, date_of_joining: dt.date,
    employment_type_id: int | None, employee_category_id: int | None, work_location_id: int | None,
    confirmation_date: dt.date | None, user: User,
) -> EmploymentEpisode:
    if candidate.status == CandidateStatus.CONVERTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This candidate has already been converted to an employee")
    if candidate.status != CandidateStatus.APPROVED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Candidate must be approved before conversion to employee")
    if not all_mandatory_passed(db, candidate):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This candidate has not passed all mandatory selection criteria yet")
    if db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == employee_number).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Employee Number already in use")

    employee = Employee(
        first_name=candidate.first_name, middle_name=candidate.middle_name, last_name=candidate.last_name,
        father_husband_name=candidate.father_husband_name, gender=candidate.gender, date_of_birth=candidate.date_of_birth,
        mobile_number=candidate.mobile_number, alternate_mobile_number=candidate.alternate_mobile_number,
        personal_email=candidate.personal_email, educational_qualification=candidate.educational_qualification,
        total_experience_years=candidate.total_experience_years,
        aadhaar=candidate.aadhaar, aadhaar_name=candidate.aadhaar_name, aadhaar_dob=candidate.aadhaar_dob,
        pan=candidate.pan, pan_name=candidate.pan_name, pan_dob=candidate.pan_dob,
        # The candidate's CURRENT employer at application time becomes
        # their PREVIOUS employer once they're hired here.
        previous_designation=candidate.current_designation, previous_company_name=candidate.current_company_name,
        previous_company_details=candidate.current_company_details, previous_date_of_joining=candidate.current_date_of_joining,
    )
    db.add(employee)
    db.flush()

    episode = EmploymentEpisode(
        employee_id=employee.id, employee_number=employee_number,
        employee_category_id=employee_category_id or candidate.applied_employee_category_id, employment_type_id=employment_type_id,
        designation_id=candidate.applied_designation_id, work_location_id=work_location_id,
        date_of_joining=date_of_joining, confirmation_date=confirmation_date,
        application_reference_number=candidate.reference_number,
        status="DRAFT",
    )
    db.add(episode)
    db.flush()

    # Organizational Assignment (Department) isn't captured during
    # recruitment (candidate.applied_department_id is legacy/unused) - HR
    # completes that in the wizard after conversion. Cost Center/Project
    # ARE captured, and cost allocation is independent of org assignment
    # in this codebase's model (blueprint §6), so they land as a 100%
    # CostAllocation row straight away.
    employee_service.add_cost_allocation(db, episode.id, {
        "cost_center_id": candidate.applied_cost_center_id,
        "project_id": candidate.applied_project_id,
        "percentage": 100,
        "effective_from": date_of_joining,
    })

    for csc in candidate.salary_components:
        payroll_service.set_salary_structure_component(
            db, episode.id, csc.component_id, csc.amount, csc.percentage, date_of_joining, user, formula=csc.formula,
        )

    document_service.copy_candidate_documents_to_episode(db, candidate, episode, user)

    if any([
        candidate.dl_licence_number, candidate.dl_badge_number, candidate.dl_vehicle_class,
        candidate.dl_issuing_authority, candidate.dl_issue_date, candidate.dl_expiry_date,
    ]):
        db.add(DrivingLicenceDetail(
            episode_id=episode.id, licence_number=candidate.dl_licence_number, badge_number=candidate.dl_badge_number,
            vehicle_class=candidate.dl_vehicle_class, issuing_authority=candidate.dl_issuing_authority,
            issue_date=candidate.dl_issue_date, expiry_date=candidate.dl_expiry_date,
        ))

    candidate.status = CandidateStatus.CONVERTED
    candidate.converted_employee_id = employee.id
    candidate.converted_episode_id = episode.id
    db.add(candidate)

    audit_service.record(db, "CANDIDATE", candidate.id, AuditAction.UPDATE, user, new_value=f"converted to episode {episode.id}")
    audit_service.record(db, "EMPLOYMENT_EPISODE", episode.id, AuditAction.CREATE, user, new_value=f"converted from candidate {candidate.reference_number}")
    return episode
