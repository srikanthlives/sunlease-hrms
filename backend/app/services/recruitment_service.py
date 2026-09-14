import datetime as dt
import os
import re

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import AuditAction, CandidateStatus
from app.models.models import (
    Candidate, CandidateSalaryComponent, CandidateStageResult, DesignationCriteria,
    Employee, EmploymentEpisode, SelectionCriteria, User,
)
from app.services import audit_service, document_service, employee_service, payroll_service


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip()).strip("-").lower()
    return value or "file"


def generate_reference_number(db: Session, candidate_id: int) -> str:
    return f"CAND-{candidate_id:05d}"


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
    other Candidate already carrying this Aadhaar number - a warning, not
    a hard block (see Candidate.aadhaar's docstring): the same person
    could legitimately be re-applying, or it could be a genuine
    data-entry mistake HR needs to see and judge for itself."""
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

    if candidate.status == CandidateStatus.APPLIED:
        candidate.status = CandidateStatus.IN_PROGRESS
        db.add(candidate)
    audit_service.record(db, "CANDIDATE_STAGE_RESULT", candidate.id, AuditAction.UPDATE, user, new_value=f"{criteria.name}={result}")
    return row


def convert_to_employee(
    db: Session, candidate: Candidate, employee_number: str, date_of_joining: dt.date,
    employment_type_id: int | None, employee_category_id: int | None, work_location_id: int | None,
    confirmation_date: dt.date | None, user: User,
) -> EmploymentEpisode:
    if candidate.status == CandidateStatus.CONVERTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This candidate has already been converted to an employee")
    if not all_mandatory_passed(db, candidate):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This candidate has not passed all mandatory selection criteria yet")
    if db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == employee_number).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Employee Number already in use")

    employee = Employee(
        first_name=candidate.first_name, middle_name=candidate.middle_name, last_name=candidate.last_name,
        father_husband_name=candidate.father_husband_name, gender=candidate.gender, date_of_birth=candidate.date_of_birth,
        mobile_number=candidate.mobile_number, alternate_mobile_number=candidate.alternate_mobile_number,
        personal_email=candidate.personal_email, educational_qualification=candidate.educational_qualification,
        total_experience_years=candidate.total_experience_years, aadhaar=candidate.aadhaar,
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

    candidate.status = CandidateStatus.CONVERTED
    candidate.converted_employee_id = employee.id
    candidate.converted_episode_id = episode.id
    db.add(candidate)

    audit_service.record(db, "CANDIDATE", candidate.id, AuditAction.UPDATE, user, new_value=f"converted to episode {episode.id}")
    audit_service.record(db, "EMPLOYMENT_EPISODE", episode.id, AuditAction.CREATE, user, new_value=f"converted from candidate {candidate.reference_number}")
    return episode
