from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_hr_admin, require_super_admin
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.enums import AuditAction, Permission, RoleName
from app.models.models import User, Role
from app.schemas.auth import PasswordResetRequest, SetActiveRequest, Token, UserCreate, UserOut, UserUpdate
from app.services import audit_service, permission_service


def _is_admin_role(role_name: str) -> bool:
    return role_name in (RoleName.HR_ADMIN, RoleName.SUPER_ADMIN)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _to_user_out(db: Session, user: User) -> UserOut:
    permissions = Permission.ALL if user.role.name in (RoleName.HR_ADMIN, RoleName.SUPER_ADMIN) else [
        g.permission_code for g in permission_service.role_permission_grants(db, user.role_id)
    ]
    return UserOut(
        id=user.id, username=user.username, email=user.email, full_name=user.full_name,
        role=user.role.name, employee_id=user.employee_id, is_active=user.is_active,
        permissions=permissions,
    )


def _log_auth(msg: str):
    # Plain print with an [AUTH] prefix, matching this codebase's existing
    # [STARTUP]/[EMAIL]-style diagnostics convention (nothing configures a
    # logging handler/level, so stdlib `logging` calls would silently
    # vanish) - visible in `docker logs`/Railway logs, so a "works locally,
    # fails in production" login report has a concrete server-side cause
    # instead of just the client's generic "Incorrect username or
    # password" (kept generic on purpose, to not leak which part - username
    # vs password vs account-disabled - was wrong to an attacker).
    print(f"[AUTH] {msg}", flush=True)


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    username = form_data.username.strip()
    if username != form_data.username:
        _log_auth(f"login attempt for {form_data.username!r} - username had leading/trailing whitespace, using {username!r}")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        _log_auth(f"login FAILED for {username!r}: no user with this username exists")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")

    if not user.hashed_password:
        _log_auth(f"login FAILED for {username!r} (user id={user.id}): hashed_password is empty/null in the database")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")

    if not verify_password(form_data.password, user.hashed_password):
        _log_auth(
            f"login FAILED for {username!r} (user id={user.id}, role={user.role.name if user.role else None}): "
            f"password did not match (see any verify_password error logged just above if the hash itself was malformed)"
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")

    if not user.is_active:
        _log_auth(f"login REJECTED for {username!r} (user id={user.id}): account is_active=False")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is disabled")

    _log_auth(f"login OK for {username!r} (user id={user.id}, role={user.role.name if user.role else None})")
    token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.name})
    audit_service.record(db, "USER", user.id, AuditAction.LOGIN, user)
    db.commit()
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_user_out(db, user)


@router.post("/users", response_model=UserOut, dependencies=[Depends(require_hr_admin)])
def create_user(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username already exists")
    role = db.query(Role).filter(Role.id == payload.role_id).first()
    if not role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role_id")
    user = User(
        username=payload.username, email=payload.email, full_name=payload.full_name,
        hashed_password=hash_password(payload.password), role_id=payload.role_id,
        employee_id=payload.employee_id,
    )
    db.add(user)
    db.flush()
    audit_service.record(db, "USER", user.id, AuditAction.CREATE, actor, new_value=role.name)
    db.commit()
    db.refresh(user)
    return _to_user_out(db, user)


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_hr_admin)])
def list_users(db: Session = Depends(get_db)):
    return [_to_user_out(db, u) for u in db.query(User).order_by(User.username).all()]


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.put("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_hr_admin)])
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """Edits username/email/full_name/role. An HR_ADMIN/SUPER_ADMIN
    account (its own role, or the one it's being reassigned to) can only
    be touched by a SUPER_ADMIN - mirrors sunlease-expms's equivalent
    Admin/Super-Admin guard, since an HR_ADMIN could otherwise promote
    itself (or another HR_ADMIN) to SUPER_ADMIN, or edit a SUPER_ADMIN's
    account without SUPER_ADMIN's own exclusive gate ever being checked."""
    user = _get_user_or_404(db, user_id)
    actor_is_super_admin = actor.role.name == RoleName.SUPER_ADMIN

    if _is_admin_role(user.role.name) and not actor_is_super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Super Admin can edit an HR Admin or Super Admin account")

    updates = payload.model_dump(exclude_unset=True)

    if "role_id" in updates and updates["role_id"] != user.role_id:
        new_role = db.query(Role).filter(Role.id == updates["role_id"]).first()
        if not new_role:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role_id")
        if _is_admin_role(new_role.name) and not actor_is_super_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Super Admin can assign the HR Admin or Super Admin role")

    if "username" in updates and updates["username"] != user.username:
        if db.query(User).filter(User.username == updates["username"], User.id != user.id).first():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username already exists")

    for field, value in updates.items():
        setattr(user, field, value)
    db.add(user)
    audit_service.record(db, "USER", user.id, AuditAction.UPDATE, actor)
    db.commit()
    db.refresh(user)
    return _to_user_out(db, user)


@router.post("/users/{user_id}/reset-password", dependencies=[Depends(require_super_admin)])
def reset_password(user_id: int, payload: PasswordResetRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """Super-Admin-only, same as sunlease-expms: the admin types the new
    password directly (no auto-generation, no email) and communicates it
    to the user out of band - never logged or echoed back."""
    user = _get_user_or_404(db, user_id)
    user.hashed_password = hash_password(payload.new_password)
    db.add(user)
    audit_service.record(db, "USER", user.id, AuditAction.UPDATE, actor, new_value="password_reset")
    db.commit()
    return {"detail": f"Password reset for {user.username}"}


@router.post("/users/{user_id}/set-active", response_model=UserOut, dependencies=[Depends(require_hr_admin)])
def set_active(user_id: int, payload: SetActiveRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """This is the disable/enable mechanism - always per-user, never
    per-role (a Role is a shared definition many users reference; there's
    no meaningful "disabled role" concept distinct from disabling each of
    its users). Same guards as update_user: only a Super Admin can
    disable an HR Admin/Super Admin account, and nobody can disable
    themself (would lock them out with no way back in for a
    non-Super-Admin)."""
    user = _get_user_or_404(db, user_id)
    if user.id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot disable your own account")
    if _is_admin_role(user.role.name) and actor.role.name != RoleName.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Super Admin can disable an HR Admin or Super Admin account")

    user.is_active = payload.is_active
    db.add(user)
    audit_service.record(db, "USER", user.id, AuditAction.STATUS_CHANGE, actor, new_value="active" if payload.is_active else "disabled")
    db.commit()
    db.refresh(user)
    return _to_user_out(db, user)


@router.get("/roles", response_model=list[dict], dependencies=[Depends(require_hr_admin)])
def list_roles(db: Session = Depends(get_db)):
    return [{"id": r.id, "name": r.name} for r in db.query(Role).order_by(Role.name).all()]
