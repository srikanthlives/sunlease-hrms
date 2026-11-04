"""Machine-to-machine endpoints: authenticated by a service token, not a user.

Kept in its own router because every other router depends on
`get_current_user` at router level, and a service token must not satisfy that.
The paths live under /api/v1/integrations so they can never collide with a
user-facing route such as /api/v1/employees/{episode_id}.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_service_token
from app.core.scopes import EMPLOYEES_EXPORT
from app.db.session import get_db
from app.services import depot_export_service

DEPOT_SCOPE = EMPLOYEES_EXPORT

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.get("/employees")
def depot_employees(db: Session = Depends(get_db), _=Depends(require_service_token(DEPOT_SCOPE))):
    """The operating crew, in the depot app's vocabulary. Read-only."""
    return {"employees": depot_export_service.employees(db)}


@router.get("/employees/rules")
def depot_employee_rules(db: Session = Depends(get_db), _=Depends(require_service_token(DEPOT_SCOPE))):
    """Which category/designation pairs are being exported, and whether those
    masters still exist under those names - so a rename is visible rather than
    silently emptying the feed."""
    return depot_export_service.selectable(db)


# The feed was first published as /depot-employees. Kept as an undocumented
# alias so an already-deployed depot app does not break the moment this
# renames; drop both aliases once every consumer is on /employees.
router.add_api_route("/depot-employees", depot_employees, methods=["GET"],
                     include_in_schema=False, deprecated=True)
router.add_api_route("/depot-employees/rules", depot_employee_rules, methods=["GET"],
                     include_in_schema=False, deprecated=True)
