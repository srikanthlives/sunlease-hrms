"""The Candidates list, as one reusable row builder.

Lifted out of routers/recruitment.py's GET /candidates handler so the Excel
export (services/export_service.py) serves exactly the rows the list page
shows, rather than a second query that could drift from it.
"""
from sqlalchemy.orm import Session

from app.models.models import Candidate, User
from app.services import document_service, permission_service, recruitment_service


def summary_dict(c: Candidate) -> dict:
    return {
        "id": c.id, "reference_number": c.reference_number,
        "first_name": c.first_name, "last_name": c.last_name,
        "applied_designation_id": c.applied_designation_id, "designation_name": c.designation.name if c.designation else None,
        "applied_cost_center_id": c.applied_cost_center_id, "cost_center_name": c.cost_center.name if c.cost_center else None,
        "applied_project_id": c.applied_project_id, "applied_project_name": c.project.name if c.project else None,
        "applied_employee_category_id": c.applied_employee_category_id,
        "applied_employee_category_name": c.employee_category.name if c.employee_category else None,
        "applied_date": c.applied_date, "status": c.status,
        "interest_status": c.interest_status, "not_interested_date": c.not_interested_date,
        "mobile_number": c.mobile_number, "aadhaar": c.aadhaar, "pan": c.pan, "dl_licence_number": c.dl_licence_number,
        # Extra list-view columns (hidden by default in the UI).
        "gender": c.gender, "date_of_birth": c.date_of_birth, "alternate_mobile_number": c.alternate_mobile_number,
        "personal_email": c.personal_email, "educational_qualification": c.educational_qualification,
        "total_experience_years": c.total_experience_years, "current_designation": c.current_designation,
        "current_company_name": c.current_company_name, "source": c.source, "remarks": c.remarks, "created_at": c.created_at,
    }


def list_rows(
    db: Session, user: User, status: str | None = None, designation_id: int | None = None,
    cost_center_id: int | None = None,
) -> list[dict]:
    """One dict per Candidate the caller is allowed to see, newest first."""
    query = db.query(Candidate)
    allowed = permission_service.user_cost_center_ids(db, user)
    if allowed is not None:
        query = query.filter(Candidate.applied_cost_center_id.in_(allowed))
    if status:
        query = query.filter(Candidate.status == status)
    if designation_id is not None:
        query = query.filter(Candidate.applied_designation_id == designation_id)
    if cost_center_id is not None:
        query = query.filter(Candidate.applied_cost_center_id == cost_center_id)
    rows = query.order_by(Candidate.created_at.desc()).all()
    out = []
    for c in rows:
        criteria = recruitment_service.criteria_status(db, c)
        mandatory_criteria = [r for r in criteria if r["is_mandatory"]]
        required_docs = document_service.resolve_required_documents_for_candidate(db, c)
        mandatory_docs = [d for d in required_docs if d["is_mandatory"]]
        out.append({
            **summary_dict(c),
            # Counts for the list view's Documents/Tests button badges - the
            # full lists (which documents/tests, uploaded or not) are fetched
            # on demand from GET /candidates/{id} when a popup is opened,
            # rather than carried on every row here.
            "documents_uploaded_count": len(c.documents),
            "documents_all_mandatory_uploaded": bool(mandatory_docs) and all(d["uploaded"] for d in mandatory_docs),
            "tests_recorded_count": sum(1 for r in criteria if r["result"] != "PENDING"),
            "tests_total_count": len(criteria),
            "tests_all_mandatory_passed": bool(mandatory_criteria) and all(r["result"] in ("PASS", "EXCEPTION") for r in mandatory_criteria),
        })
    return out
