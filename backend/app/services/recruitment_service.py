import datetime as dt
import json
import os
import re
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.enums import AuditAction, CandidateStatus, RoleName, TransactionType
from app.models.models import (
    Address, Candidate, CandidateChangeRequest, CandidateDocument, CandidateStageResult,
    DesignationCriteria, DrivingLicenceDetail, Employee, EmploymentEpisode, SelectionCriteria,
    SharedCriteriaAttachment, User,
)
from app.services import approval_service, audit_service, criteria_rule_service, document_service, employee_service
from app.services.storage import get_storage


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip()).strip("-").lower()
    return value or "file"


def generate_reference_number(db: Session, candidate: Candidate) -> str:
    """Company code / Cost Center code / Project code / Employee Category /
    sequence-within-that-scope, e.g. "SUNLEASE/CC-PDY/PRJ-01/DRIVER/003".
    The Project segment is omitted when the candidate has no
    applied_project_id (a candidate can still legitimately have no
    project even though Cost Center/Category are mandatory - a Project is
    optional org structure). Employee Category has no separate "code"
    field the way Company/Cost Center/Project do, so its name is used
    directly (already uppercase per this app's input convention) with
    spaces collapsed to hyphens. Falls back to "NA" for a missing
    Company/Cost Center/Category (legacy rows created before those
    columns were required) rather than raising - a reference number
    should never block candidate creation."""
    cost_center = candidate.cost_center
    company = cost_center.company if cost_center else None
    company_code = (company.code if company else None) or "NA"
    cost_center_code = (cost_center.code if cost_center else None) or "NA"
    project_code = candidate.project.code if candidate.project else None
    category_name = (candidate.employee_category.name if candidate.employee_category else None) or "NA"
    category_segment = re.sub(r"\s+", "-", category_name.strip())

    scope_query = db.query(Candidate).filter(
        Candidate.applied_cost_center_id == candidate.applied_cost_center_id,
        Candidate.applied_project_id == candidate.applied_project_id,
        Candidate.applied_employee_category_id == candidate.applied_employee_category_id,
        Candidate.id != candidate.id,
    )
    sequence = scope_query.count() + 1

    prefix = [company_code, cost_center_code]
    if project_code:
        prefix.append(project_code)
    prefix.append(category_segment)
    # Candidates can leave a scope (Cost Center/Project edit or transfer)
    # while keeping their reference number, so count+1 may already be
    # taken - skip forward until it's free.
    while True:
        reference = "/".join(prefix + [f"{sequence:03d}"])
        if not db.query(Candidate.id).filter(Candidate.reference_number == reference, Candidate.id != candidate.id).first():
            return reference
        sequence += 1


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
        .filter(DesignationCriteria.is_active.is_(True))
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
            "attachment_file_name": _effective_attachment_name(result),
            "attachment_mime_type": _effective_attachment_mime(result),
            "attachment_is_shared": bool(result and not result.attachment_object_key and result.shared_attachment_id),
            "is_auto": criteria_rule_service.is_auto(req.criteria) if req.criteria else False,
            "auto_rule": criteria_rule_service.describe(req.criteria) if req.criteria else None,
            "auto_reason": result.auto_reason if result else None,
            "supports_bulk_upload": bool(req.criteria and req.criteria.supports_bulk_upload),
            "requires_attachment": not req.criteria or req.criteria.requires_attachment is not False,
        })
    return out


def _effective_attachment_name(result: CandidateStageResult | None) -> str | None:
    """A stage result's proof is its own uploaded file if it has one, else
    the shared document it points at. Own file wins so that a per-candidate
    re-upload can always supersede a bulk-filed report for that one person
    without disturbing the others."""
    if not result:
        return None
    if result.attachment_object_key:
        return result.attachment_file_name
    return result.shared_attachment.file_name if result.shared_attachment else None


def _effective_attachment_mime(result: CandidateStageResult | None) -> str | None:
    if not result:
        return None
    if result.attachment_object_key:
        return result.attachment_mime_type
    return result.shared_attachment.mime_type if result.shared_attachment else None


def effective_attachment(result: CandidateStageResult) -> tuple[str, str | None, str | None] | None:
    """(object_key, mime_type, file_name) of whichever proof applies, or None."""
    if result.attachment_object_key:
        return result.attachment_object_key, result.attachment_mime_type, result.attachment_file_name
    if result.shared_attachment:
        shared = result.shared_attachment
        return shared.object_key, shared.mime_type, shared.file_name
    return None


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
    exclude_candidate_id: int | None = None, exclude_employee_id: int | None = None,
) -> None:
    """Hard-blocks creating/updating a candidate whose Aadhaar, PAN, or
    Driving Licence Number matches an existing Employee or another
    Candidate - unlike the informational aadhaar_duplicate_warning this
    replaces, these three are treated as unique identifiers that can
    never legitimately collide between two different people, so there's
    nothing for HR to "judge" the way there might be for a name/mobile
    match; the row is simply rejected.

    exclude_employee_id: a requalified candidate (see requalify_candidate)
    that was previously CONVERTED already has an Employee row carrying
    these exact identifiers - that's their own past self, not a
    collision, so routers/recruitment.py passes
    candidate.converted_employee_id here when editing one."""
    errors = []

    if aadhaar:
        employee_query = db.query(Employee).filter(Employee.aadhaar == aadhaar)
        if exclude_employee_id:
            employee_query = employee_query.filter(Employee.id != exclude_employee_id)
        matches = _find_matches(db, employee_query, db.query(Candidate).filter(Candidate.aadhaar == aadhaar), exclude_candidate_id)
        if matches:
            errors.append(f"Aadhaar Number already used by {matches[0]}")

    if pan:
        employee_query = db.query(Employee).filter(Employee.pan == pan)
        if exclude_employee_id:
            employee_query = employee_query.filter(Employee.id != exclude_employee_id)
        matches = _find_matches(db, employee_query, db.query(Candidate).filter(Candidate.pan == pan), exclude_candidate_id)
        if matches:
            errors.append(f"PAN Number already used by {matches[0]}")

    if dl_licence_number:
        employee_matches = [
            f"Employee: {r.episode.employee.first_name} {r.episode.employee.last_name}"
            for r in db.query(DrivingLicenceDetail).filter(DrivingLicenceDetail.licence_number == dl_licence_number).all()
            if r.episode and r.episode.employee and r.episode.employee_id != exclude_employee_id
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


def can_review(db: Session, user: User, candidate: Candidate, transaction_type: str = TransactionType.RECRUITMENT_APPROVAL) -> bool:
    """Whether `user` is allowed to approve/send back this candidate (or, with
    RECRUITMENT_CHANGE, its change requests) - the same routing check the
    approve endpoints enforce, exposed so the UI only offers the buttons to
    people who can actually use them."""
    try:
        authorize_candidate_approval(db, user, candidate, transaction_type)
        return True
    except HTTPException:
        return False


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


def release_conversion(db: Session, candidate: Candidate, employee_id: int | None, user: User) -> None:
    """The employment episode this candidate was converted into has just
    been deleted - undo the conversion on the candidate side.

    Called from routers/employees.py::delete_draft. Without this the
    candidate stays CONVERTED pointing at an episode that no longer exists,
    which shows up as a dead "View employee record" link and leaves
    Requalify as the only available action.

    Status goes back to **APPROVED**, not APPLIED: this candidate had
    already passed every mandatory criterion and been approved, and
    deleting the episode undoes only the conversion, so they return to
    exactly the state they were in the moment before it and can simply be
    converted again. (Requalify -> APPLIED is for the genuinely different
    case of someone who was employed, left, and is reapplying.)

    `converted_employee_id` is kept when that Employee row still exists -
    the person survives a deleted stint if they had others - so a
    re-conversion reattaches to the same person instead of creating a
    duplicate, which convert_to_employee relies on. It is cleared only
    when the Employee was purged along with the episode.
    """
    person_survives = (
        employee_id is not None
        and db.query(Employee).filter(Employee.id == employee_id).first() is not None
    )
    previous_status = candidate.status
    candidate.converted_episode_id = None
    if not person_survives:
        candidate.converted_employee_id = None
    if candidate.status == CandidateStatus.CONVERTED:
        candidate.status = CandidateStatus.APPROVED
    db.add(candidate)
    audit_service.record(
        db, "CANDIDATE", candidate.id, AuditAction.STATUS_CHANGE, user,
        old_value=previous_status,
        new_value=f"{candidate.status} (converted employment record deleted"
                  + ("" if person_survives else "; person record deleted too") + ")",
    )


def requalify_candidate(db: Session, candidate: Candidate, user: User) -> None:
    """Puts a REJECTED or CONVERTED candidate back to square one (APPLIED)
    to be reconsidered through the full pipeline again - re-editable,
    resubmittable, and re-testable on every Selection Criteria (existing
    PASS/FAIL/EXCEPTION results from the earlier round are left as-is,
    visible as history, but every criteria can simply be re-marked).

    For a CONVERTED candidate specifically, this is the "rejoiner"
    case - someone who resigned/was separated and is now reapplying.
    converted_employee_id/converted_episode_id are deliberately left in
    place rather than cleared: they're a breadcrumb to the person's prior
    employment, and the candidate's own UI only reads them while
    status == CONVERTED (see CandidateDetail.jsx's isConverted banner),
    so leaving them set here causes no confusion once status moves on.
    Re-converting this same candidate later REATTACHES to the same
    Employee and opens a new EmploymentEpisode under it (see
    convert_to_employee's `prior`/`converted_employee_id` branch), which
    is why the breadcrumb matters - it is what stops a rejoiner becoming a
    duplicate person."""
    if candidate.status not in (CandidateStatus.REJECTED, CandidateStatus.CONVERTED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a Rejected or Converted candidate can be requalified")
    previous_status = candidate.status
    candidate.status = CandidateStatus.APPLIED
    db.add(candidate)
    audit_service.record(db, "CANDIDATE", candidate.id, AuditAction.STATUS_CHANGE, user, old_value=previous_status, new_value="APPLIED (requalified)")


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
    db.flush()
    audit_service.record(db, "CANDIDATE", candidate.id, AuditAction.UPDATE, user)
    # The edit may well be the date an automatic rule reads.
    reevaluate_auto_criteria(db, candidate, user)
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

    changes = json.loads(request.changes_json)
    if approve:
        if request.request_type == "FIELD_CHANGE":
            for field, value in changes.items():
                setattr(candidate, field, value)
            db.add(candidate)
            db.flush()
            # An APPROVED candidate's edits land here rather than in
            # save_or_request_candidate_update, so this is the other half of
            # "re-evaluate when the data behind the rule changes".
            reevaluate_auto_criteria(db, candidate, user)
        elif request.request_type == "DOCUMENT_DELETE":
            doc = db.query(CandidateDocument).filter(CandidateDocument.id == changes["document_id"]).first()
            if doc:
                document_service.delete_candidate_document(db, doc)
        elif request.request_type == "DOCUMENT_REPLACE":
            doc = db.query(CandidateDocument).filter(CandidateDocument.id == changes["document_id"]).first()
            if doc:
                document_service.apply_staged_replacement(db, doc, changes)
        request.status = "APPROVED"
        audit_service.record(db, "CANDIDATE_CHANGE_REQUEST", request.id, AuditAction.APPROVE, user, new_value=request.changes_json)
    else:
        if request.request_type == "DOCUMENT_REPLACE":
            document_service.discard_staged_replacement(changes)
        request.status = "REJECTED"
        audit_service.record(db, "CANDIDATE_CHANGE_REQUEST", request.id, AuditAction.REJECT, user, new_value=remarks)

    db.add(request)
    return request


def all_mandatory_passed(db: Session, candidate: Candidate) -> bool:
    """All mandatory Selection Criteria must be PASS or EXCEPTION before a
    candidate can be converted to an employee - EXCEPTION covers a
    mandatory criteria HR has deliberately waived (with a remark
    explaining why) rather than the candidate genuinely passing it."""
    statuses = criteria_status(db, candidate)
    mandatory = [s for s in statuses if s["is_mandatory"]]
    return len(mandatory) > 0 and all(s["result"] in ("PASS", "EXCEPTION") for s in mandatory)


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
    stored_name = f"{stage_result.criteria_id}-{_slug(os.path.splitext(upload_file.filename or '')[0])}{ext}"
    object_key = os.path.join(document_service._candidate_upload_dir(candidate), "criteria-proofs", stored_name)

    content = upload_file.file.read()
    get_storage().save(object_key, content)

    # An individual upload supersedes any shared document this row pointed
    # at - detach first so the shared file's reference count stays honest.
    if stage_result.shared_attachment_id:
        detach_shared_attachment(db, stage_result, actor, audit=False)
    stage_result.attachment_object_key = object_key
    stage_result.attachment_file_name = upload_file.filename
    stage_result.attachment_mime_type = upload_file.content_type
    db.add(stage_result)
    audit_service.record(db, "CANDIDATE_STAGE_RESULT", stage_result.id, AuditAction.UPDATE, actor, new_value=f"attachment uploaded for criteria {stage_result.criteria_id}")
    return stage_result


def delete_stage_result_attachment(db: Session, stage_result: CandidateStageResult, actor: User) -> None:
    """Removes the proof file from disk as well as clearing the DB
    columns - same "clean the repository of deleted documents" convention
    as document_service.delete_candidate_document. The result itself
    (PASS/FAIL/EXCEPTION, tested_on, remarks) is untouched - only the
    attachment goes."""
    if stage_result.shared_attachment_id and not stage_result.attachment_object_key:
        detach_shared_attachment(db, stage_result, actor)
        return
    if stage_result.attachment_object_key:
        get_storage().delete(stage_result.attachment_object_key)
    stage_result.attachment_object_key = None
    stage_result.attachment_file_name = None
    stage_result.attachment_mime_type = None
    db.add(stage_result)
    audit_service.record(db, "CANDIDATE_STAGE_RESULT", stage_result.id, AuditAction.UPDATE, actor, old_value=f"attachment removed for criteria {stage_result.criteria_id}")


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
    # A person decided this one. On an automatic criteria that only ever
    # happens for an EXCEPTION (the router refuses a manual PASS/FAIL), and
    # clearing is_auto is what stops the next re-evaluation overwriting the
    # waiver - without it the rule would quietly undo HR's decision.
    row.is_auto = False
    row.auto_reason = None
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
    # Re-checked here and not only on edit: an expiry-based rule can go stale
    # with nobody touching the candidate, and conversion is the moment that
    # actually costs something.
    reevaluate_auto_criteria(db, candidate, user)
    if not all_mandatory_passed(db, candidate):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This candidate has not passed (or been marked EXCEPTION for) all mandatory selection criteria yet")
    # A requalified candidate who was previously converted is a REJOINER:
    # re-attach to the same Employee (never a duplicate person) and reuse
    # their employee number on a new stint. Identity fields on the existing
    # Employee are left as they are.
    prior = None
    employee = db.query(Employee).filter(Employee.id == candidate.converted_employee_id).first() if candidate.converted_employee_id else None
    if employee:
        prior = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_id == employee.id).order_by(EmploymentEpisode.id.desc()).first()
        if prior and prior.status != "SEPARATED":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "This person still has a current employment record - use Transfer on their employee record to move them to another Cost Center",
            )
        # An employee number identifies a person within a Cost Center: coming
        # back to one they served before reuses that number.
        reuse = employee_service.number_for_cost_center(db, employee.id, candidate.applied_cost_center_id)
        if reuse:
            employee_number = reuse[0]
        employee_service.check_number_available(db, employee_number, employee.id, candidate.applied_cost_center_id)
    elif db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == employee_number).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Employee Number already in use")

    if not employee:
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

        # Present/Permanent Address becomes the employee's own structured
        # Address rows (one PRESENT, one PERMANENT) - only for a brand-new
        # Employee; a rejoiner already has their own Address rows from
        # their prior stint, left untouched.
        fields = ("line1", "line2", "city", "state", "pincode", "country")
        present_values = {f: getattr(candidate, f"present_{f}") for f in fields}
        permanent_values = present_values if candidate.same_as_present else {f: getattr(candidate, f"permanent_{f}") for f in fields}
        if any(present_values.values()):
            db.add(Address(employee_id=employee.id, address_type="PRESENT", **present_values))
        if any(permanent_values.values()):
            db.add(Address(employee_id=employee.id, address_type="PERMANENT", **permanent_values))

    episode = EmploymentEpisode(
        employee_id=employee.id, employee_number=employee_number,
        employee_category_id=employee_category_id or candidate.applied_employee_category_id, employment_type_id=employment_type_id,
        designation_id=candidate.applied_designation_id, work_location_id=work_location_id,
        date_of_joining=date_of_joining, confirmation_date=confirmation_date,
        application_reference_number=candidate.reference_number,
        previous_episode_id=prior.id if prior else None,
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


# ---------------------------------------------------------------------------
# Bulk (shared) proof documents
#
# One test, one report sheet, many candidates - e.g. a training whose single
# attendance/assessment report lists all 20 attendees. The file is uploaded
# and stored ONCE (SharedCriteriaAttachment) and every selected candidate's
# stage result points at it.
#
# This files the PROOF only. PASS/FAIL stays a per-candidate decision
# recorded the usual way, precisely because such a report normally carries
# both - marking twenty people PASS because one document covers them is the
# mistake this is meant to avoid, not a shortcut it should take.
# ---------------------------------------------------------------------------

MAX_BULK_CANDIDATES = 200


def _shared_attachment_ref_count(db: Session, shared_id: int) -> int:
    return db.query(CandidateStageResult).filter(CandidateStageResult.shared_attachment_id == shared_id).count()


def detach_shared_attachment(db: Session, stage_result: CandidateStageResult, actor: User, audit: bool = True) -> None:
    """Removes the shared proof from THIS candidate only. The stored file
    and its SharedCriteriaAttachment row survive as long as any other
    candidate still references them, and are deleted when the last one
    goes - a shared document is evidence for each candidate independently,
    so one person's cleanup must never erase nineteen others'."""
    shared_id = stage_result.shared_attachment_id
    if not shared_id:
        return
    stage_result.shared_attachment_id = None
    db.add(stage_result)
    db.flush()
    if _shared_attachment_ref_count(db, shared_id) == 0:
        shared = db.query(SharedCriteriaAttachment).filter(SharedCriteriaAttachment.id == shared_id).first()
        if shared:
            get_storage().delete(shared.object_key)
            db.delete(shared)
    if audit:
        audit_service.record(
            db, "CANDIDATE_STAGE_RESULT", stage_result.id, AuditAction.UPDATE, actor,
            old_value=f"shared attachment detached for criteria {stage_result.criteria_id}",
        )


def vet_candidate_for_bulk_attachment(db: Session, candidate: Candidate, criteria: SelectionCriteria) -> dict:
    """Read-only verdict for one candidate, used both by the preflight
    endpoint (so the dialog can grey out rows with the reason) and by the
    upload itself (so the two can never disagree) - same vet-then-apply
    shape as the employee bulk transfer's _vet_for_transfer."""
    row = {
        "candidate_id": candidate.id,
        "reference_number": candidate.reference_number,
        "name": " ".join(filter(None, [candidate.first_name, candidate.middle_name, candidate.last_name])),
        "designation": candidate.designation.name if candidate.designation else None,
        "blocked_reason": None,
        "existing_result": None,
        "existing_attachment": None,
    }
    if candidate.status != CandidateStatus.APPROVED:
        row["blocked_reason"] = f"Candidate is {candidate.status} - must be Approved before a result can be recorded"
        return row
    required = required_criteria(db, candidate.applied_designation_id, candidate.applied_cost_center_id)
    if criteria.id not in {r.criteria_id for r in required}:
        row["blocked_reason"] = f"\"{criteria.name}\" is not required for this candidate's designation"
        return row
    existing = (
        db.query(CandidateStageResult)
        .filter(CandidateStageResult.candidate_id == candidate.id, CandidateStageResult.criteria_id == criteria.id)
        .first()
    )
    if existing:
        row["existing_result"] = existing.result
        row["existing_attachment"] = _effective_attachment_name(existing)
    return row


def bulk_attach_shared_proof(
    db: Session, criteria: SelectionCriteria, candidates: list[Candidate],
    upload_file: UploadFile, actor: User,
) -> dict:
    """Stores the file once and points every candidate's stage result at it.

    All-or-nothing on eligibility: the whole selection is vetted read-only
    first and, if anything in it cannot take the document, nothing is
    stored and every reason comes back in one 400 - the same rule as the
    bulk transfer, and for the same reason (a half-filed report leaves no
    record of which half went through)."""
    if not criteria.supports_bulk_upload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"\"{criteria.name}\" is not configured for bulk upload")
    if not candidates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select at least one candidate")
    if len(candidates) > MAX_BULK_CANDIDATES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"At most {MAX_BULK_CANDIDATES} candidates can be attached in one upload")

    verdicts = [vet_candidate_for_bulk_attachment(db, c, criteria) for c in candidates]
    blocked = [v for v in verdicts if v["blocked_reason"]]
    if blocked:
        detail = "; ".join(f"{v['reference_number'] or v['candidate_id']}: {v['blocked_reason']}" for v in blocked[:10])
        more = f" (and {len(blocked) - 10} more)" if len(blocked) > 10 else ""
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Nothing was uploaded. {len(blocked)} of {len(candidates)} cannot take this document - {detail}{more}",
        )

    content = upload_file.file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")
    ext = os.path.splitext(upload_file.filename or "")[1]
    stamp = dt.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    # The random segment is not decoration: two uploads of the same report in
    # the same second would otherwise land on one object_key, and releasing
    # the superseded SharedCriteriaAttachment would delete the file the new
    # one is using. Each shared document owns its own stored object.
    unique = uuid.uuid4().hex[:8]
    stored_name = f"{stamp}-{unique}-{_slug(os.path.splitext(upload_file.filename or '')[0])}{ext}"
    object_key = os.path.join("criteria-proofs-shared", str(criteria.id), stored_name)
    get_storage().save(object_key, content)

    shared = SharedCriteriaAttachment(
        criteria_id=criteria.id, file_name=upload_file.filename, object_key=object_key,
        mime_type=upload_file.content_type, file_size=len(content), uploaded_by_id=actor.id,
    )
    db.add(shared)
    db.flush()

    attached = []
    for candidate in candidates:
        row = (
            db.query(CandidateStageResult)
            .filter(CandidateStageResult.candidate_id == candidate.id, CandidateStageResult.criteria_id == criteria.id)
            .first()
        )
        if not row:
            row = CandidateStageResult(candidate_id=candidate.id, criteria_id=criteria.id)
            db.add(row)
            db.flush()
        # Replacing whatever proof was there: an individual file of this
        # candidate's own is removed from storage, a previously shared one
        # is released through the reference count.
        if row.attachment_object_key:
            get_storage().delete(row.attachment_object_key)
            row.attachment_object_key = None
            row.attachment_file_name = None
            row.attachment_mime_type = None
        elif row.shared_attachment_id and row.shared_attachment_id != shared.id:
            detach_shared_attachment(db, row, actor, audit=False)
        row.shared_attachment_id = shared.id
        db.add(row)
        attached.append(candidate.reference_number or str(candidate.id))

    audit_service.record(
        db, "SHARED_CRITERIA_ATTACHMENT", shared.id, AuditAction.CREATE, actor,
        new_value=f"{criteria.name}: {upload_file.filename} shared by {len(attached)} candidates",
    )
    return {"shared_attachment_id": shared.id, "file_name": shared.file_name, "attached": attached, "attached_count": len(attached)}


# ---------------------------------------------------------------------------
# Automatic criteria
#
# An auto criteria's result is STORED like any other (so the candidate page,
# conversion check and audit trail all read one place), but it is owned by
# the rule rather than by a person: it is recomputed whenever the data behind
# it changes - the candidate is created or edited, a change request applying
# an edit is approved, the rule itself is edited - and again at conversion,
# because time passing is the one way a stored verdict can go stale without
# anybody touching the candidate (a licence expires on its own).
#
# A human's EXCEPTION always wins. An auto FAIL is waived the same visible
# way any other mandatory criteria is, with a remark; it is never silently
# overwritten by a manual PASS, which would leave an overridden rule looking
# identical to one that genuinely passed.
# ---------------------------------------------------------------------------

def reevaluate_auto_criteria(db: Session, candidate: Candidate, user: User | None = None) -> list[dict]:
    """Recomputes every automatic criteria that applies to this candidate.
    Safe to call as often as you like; it only writes when a verdict or its
    reason actually changed."""
    changed = []
    for req in required_criteria(db, candidate.applied_designation_id, candidate.applied_cost_center_id):
        criteria = req.criteria
        if not criteria or not criteria_rule_service.is_auto(criteria):
            continue
        result, reason = criteria_rule_service.evaluate(criteria, candidate)
        row = (
            db.query(CandidateStageResult)
            .filter(CandidateStageResult.candidate_id == candidate.id,
                    CandidateStageResult.criteria_id == criteria.id)
            .first()
        )
        if row and row.result == "EXCEPTION" and not row.is_auto:
            continue                       # HR waived it; the rule does not argue
        if not row:
            row = CandidateStageResult(candidate_id=candidate.id, criteria_id=criteria.id)
            db.add(row)
        elif row.result == result and row.auto_reason == reason:
            row.auto_evaluated_at = dt.datetime.utcnow()
            continue
        else:
            changed.append({"criteria": criteria.name, "from": row.result, "to": result})
        row.is_auto = True
        row.result = result
        row.auto_reason = reason
        row.auto_evaluated_at = dt.datetime.utcnow()
        row.tested_on = dt.date.today()
        row.reviewed_by_id = None          # nobody decided this; the rule did
        db.add(row)
    if changed and user is not None:
        audit_service.record(
            db, "CANDIDATE", candidate.id, AuditAction.UPDATE, user,
            new_value="; ".join(f"{c['criteria']}: {c['from']} -> {c['to']}" for c in changed),
        )
    db.flush()
    return changed


def reevaluate_candidates_for_criteria(db: Session, criteria: SelectionCriteria, user: User | None = None) -> int:
    """After the rule itself is edited - the rule is part of "the data behind
    the evaluation". Converted and rejected candidates are left alone: their
    selection is over, and rewriting their record to match a rule written
    afterwards would be rewriting history."""
    if not criteria_rule_service.is_auto(criteria):
        return 0
    designation_ids = {
        row.designation_id for row in
        db.query(DesignationCriteria).filter(
            DesignationCriteria.criteria_id == criteria.id, DesignationCriteria.is_active.is_(True)
        ).all()
    }
    if not designation_ids:
        return 0
    candidates = (
        db.query(Candidate)
        .filter(Candidate.applied_designation_id.in_(designation_ids))
        .filter(Candidate.status.notin_([CandidateStatus.CONVERTED, CandidateStatus.REJECTED]))
        .all()
    )
    for candidate in candidates:
        reevaluate_auto_criteria(db, candidate, user)
    return len(candidates)
