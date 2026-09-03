from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.enums import RoleName
from app.models.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_roles(*role_names: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in role_names:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(role_names)}",
            )
        return user

    return checker


# Convenience shorthands used across routers. HR_ADMIN is a superset of
# every other role for Module 1 (Phase 1 has no granular field-level RBAC
# yet - see blueprint §18/§22 - so these are the coarse role gates until
# that's built out).
require_hr_admin = require_roles("HR_ADMIN")
require_hr_staff = require_roles("HR_ADMIN", "HR_STAFF")
require_approver = require_roles("HR_ADMIN", "APPROVER")
require_any = require_roles("HR_ADMIN", "HR_STAFF", "APPROVER", "EMPLOYEE")


def require_permission(code: str):
    """Granular permission gate (blueprint §18). HR_ADMIN bypasses every
    check (implicitly has every permission); every other role is checked
    against its RolePermission grants via services/permission_service."""
    def checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        from app.services.permission_service import has_permission  # local import: avoids a core<->services import cycle

        if user.role.name == RoleName.HR_ADMIN:
            return user
        if not has_permission(db, user, code):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {code}")
        return user

    return checker
