from sqlalchemy.orm import Session

from app.models.models import DrivingLicenceRequirement, EmploymentEpisode


def resolve_driving_licence_requirement(db: Session, episode: EmploymentEpisode) -> dict:
    """Whether the Driving Licence wizard step should be shown for this
    episode, matched against Employee Type / Category / Designation with
    the same most-specific-wins priority as document requirements
    (Employee Type weight 3 > Category weight 2 > Designation weight 1).
    No matching rule => step is hidden."""
    rules = db.query(DrivingLicenceRequirement).filter(DrivingLicenceRequirement.is_active.is_(True)).all()

    best = None
    best_weight = -1
    for rule in rules:
        if rule.employee_type_id is not None and rule.employee_type_id != episode.employment_type_id:
            continue
        if rule.employee_category_id is not None and rule.employee_category_id != episode.employee_category_id:
            continue
        if rule.designation_id is not None and rule.designation_id != episode.designation_id:
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
