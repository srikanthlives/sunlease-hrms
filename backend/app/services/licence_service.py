from sqlalchemy.orm import Session

from app.models.models import Candidate, DrivingLicenceRequirement, EmploymentEpisode


def _resolve_driving_licence_requirement(
    db: Session, employment_type_id: int | None, employee_category_id: int | None, designation_id: int | None,
) -> dict:
    """Whether the Driving Licence step/section should be shown, matched
    against Employee Type / Category / Designation with the same
    most-specific-wins priority as document requirements (Employee Type
    weight 3 > Category weight 2 > Designation weight 1). No matching rule
    => hidden. Shared by resolve_driving_licence_requirement (an
    EmploymentEpisode) and resolve_driving_licence_requirement_for_candidate
    (a Candidate, which has no Employee Type yet) - same rules configured
    once on the admin's Driving Licence Configuration screen apply to
    both, per the Documents precedent (document_service.py)."""
    rules = db.query(DrivingLicenceRequirement).filter(DrivingLicenceRequirement.is_active.is_(True)).all()

    best = None
    best_weight = -1
    for rule in rules:
        if rule.employee_type_id is not None and rule.employee_type_id != employment_type_id:
            continue
        if rule.employee_category_id is not None and rule.employee_category_id != employee_category_id:
            continue
        if rule.designation_id is not None and rule.designation_id != designation_id:
            continue

        weight = (
            (3 if rule.employee_type_id is not None else 0)
            + (2 if rule.employee_category_id is not None else 0)
            + (1 if rule.designation_id is not None else 0)
        )
        if weight > best_weight:
            best_weight = weight
            best = rule

    if not best:
        return {"show": False, "is_required": False}
    return {"show": True, "is_required": best.is_required}


def resolve_driving_licence_requirement(db: Session, episode: EmploymentEpisode) -> dict:
    return _resolve_driving_licence_requirement(db, episode.employment_type_id, episode.employee_category_id, episode.designation_id)


def resolve_driving_licence_requirement_for_candidate(db: Session, candidate: Candidate) -> dict:
    """A candidate has no Employee Type yet (chosen at conversion time),
    so only Category/Designation-scoped rules can match."""
    return _resolve_driving_licence_requirement(db, None, candidate.applied_employee_category_id, candidate.applied_designation_id)
