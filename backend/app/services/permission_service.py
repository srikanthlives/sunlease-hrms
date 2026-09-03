from sqlalchemy.orm import Session

from app.models.enums import RoleName, Permission
from app.models.models import RolePermission, UserCostCenterScope, User

# Fields masked out of employee API responses unless the caller has
# employee.sensitive.view (blueprint §18 - field-level access). Nested
# under "employee" (Aadhaar/PAN) vs top-level lists (bank/statutory) in
# the /employees/{id} response shape - see routers/employees.py.
SENSITIVE_EMPLOYEE_FIELDS = {"aadhaar", "pan"}
SENSITIVE_BANK_FIELDS = {"account_number", "ifsc"}
SENSITIVE_STATUTORY_FIELDS = {"uan", "esi_number", "esi_mediclaim_number"}
SENSITIVE_LICENCE_FIELDS = {"licence_number", "badge_number"}


def has_permission(db: Session, user: User, code: str) -> bool:
    if user.role.name == RoleName.HR_ADMIN:
        return True
    grant = (
        db.query(RolePermission)
        .filter(RolePermission.role_id == user.role_id, RolePermission.permission_code == code)
        .first()
    )
    return grant is not None


def role_permission_grants(db: Session, role_id: int) -> list[RolePermission]:
    return db.query(RolePermission).filter(RolePermission.role_id == role_id).all()


def user_cost_center_ids(db: Session, user: User) -> list[int] | None:
    """None means unrestricted (HR_ADMIN). Otherwise the list of Cost
    Center ids this user may see/act on - empty list means none."""
    if user.role.name == RoleName.HR_ADMIN:
        return None
    rows = db.query(UserCostCenterScope.cost_center_id).filter(UserCostCenterScope.user_id == user.id).all()
    return [r[0] for r in rows]


def can_see_cost_center(db: Session, user: User, cost_center_id: int | None) -> bool:
    allowed = user_cost_center_ids(db, user)
    if allowed is None:
        return True
    # An employee draft with no OrgAssignment yet isn't scoped to any Cost
    # Center - anyone with the base employee.* permission can work on it
    # (scoping only kicks in once it's actually assigned somewhere).
    if cost_center_id is None:
        return True
    return cost_center_id in allowed


def mask_sensitive_fields(db: Session, user: User, detail: dict) -> dict:
    if has_permission(db, user, Permission.EMPLOYEE_SENSITIVE_VIEW):
        return detail
    for field in SENSITIVE_EMPLOYEE_FIELDS:
        if field in detail.get("employee", {}):
            detail["employee"][field] = None
    for bank in detail.get("bank_accounts", []):
        for field in SENSITIVE_BANK_FIELDS:
            if field in bank:
                bank[field] = None
    for stat in detail.get("statutory", []):
        for field in SENSITIVE_STATUTORY_FIELDS:
            if field in stat:
                stat[field] = None
    for field in SENSITIVE_LICENCE_FIELDS:
        if field in detail.get("driving_licence", {}):
            detail["driving_licence"][field] = None
    return detail
