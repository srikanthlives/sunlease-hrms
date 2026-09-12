"""Super-admin-only database backup/restore tools, mirroring
sunlease-expms's identical feature. SQLite-only (this whole app has no
other DB backend today) - `_sqlite_path()` 400s cleanly if that ever
changes.

Both routes are gated by `require_super_admin`, a strictly narrower gate
than `require_hr_admin` - HR_ADMIN itself cannot reach these, only the
dedicated SUPER_ADMIN role can (see models/enums.py::RoleName)."""
import datetime as dt
import os
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_super_admin
from app.db.session import SessionLocal, engine, get_db
from app.migrate import migrate
from app.models.enums import AuditAction
from app.models.models import User
from app.services import audit_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_super_admin)])

SQLITE_MAGIC = b"SQLite format 3\x00"


def _sqlite_path() -> str:
    if not settings.DATABASE_URL.startswith("sqlite"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Database backup/restore is only supported for SQLite deployments")
    return settings.DATABASE_URL.split("sqlite:///", 1)[1]


@router.get("/db-backup")
def download_db_backup(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    path = _sqlite_path()
    if not os.path.exists(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Database file not found")

    # Flush any WAL-mode pending writes into the main file first, so the
    # downloaded snapshot is complete/consistent rather than missing
    # recent writes that are still sitting in the WAL journal.
    with engine.connect() as conn:
        conn.execute(text("PRAGMA wal_checkpoint(FULL)"))

    audit_service.record(db, "SYSTEM", 0, AuditAction.UPDATE, actor, new_value="db_backup_downloaded")
    db.commit()

    filename = f"hrms-backup-{dt.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.db"
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@router.post("/db-restore")
def restore_db_backup(file: UploadFile = File(...), confirm: str = Form(...), actor: User = Depends(get_current_user)):
    if confirm != "REPLACE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type REPLACE to confirm this destructive action")

    # Captured before any destructive step, purely as a plain int - `actor`
    # itself is an ORM object bound to a session/connection this request's
    # own engine.dispose() call (below) will invalidate, so it must never
    # be touched again after the swap. Re-fetched via a fresh session
    # instead of reused directly.
    actor_id = actor.id

    path = _sqlite_path()
    content = file.file.read()
    if content[:16] != SQLITE_MAGIC:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is not a valid SQLite database")

    # Validate on a throwaway copy first - never touch the live file until
    # the uploaded one has proven itself intact.
    tmp_path = f"{path}.upload.tmp"
    with open(tmp_path, "wb") as f:
        f.write(content)

    tmp_engine = create_engine(f"sqlite:///{tmp_path}")
    try:
        with tmp_engine.connect() as conn:
            result = conn.execute(text("PRAGMA integrity_check")).scalar()
        if result != "ok":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Uploaded database failed integrity check: {result}")
    finally:
        tmp_engine.dispose()

    # Keep an untouched, timestamped copy of the current database - never
    # deleted automatically, so a bad restore is always recoverable by hand.
    if os.path.exists(path):
        backup_path = f"{path}.before-restore-{dt.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(path, backup_path)

    # Release this process's pooled connections/file handles on the
    # current sqlite file before replacing it, then atomically swap in
    # the new one - no app restart needed.
    engine.dispose()
    shutil.move(tmp_path, path)

    # Bring an older uploaded schema up to date the same additive way
    # normal startup does.
    migrate(verbose=False)

    # Fresh session opened AFTER the swap, so this audit entry lands in
    # the newly-restored database rather than a stale connection still
    # pointing at the old file object.
    db = SessionLocal()
    try:
        fresh_actor = db.query(User).filter(User.id == actor_id).first()
        audit_service.record(db, "SYSTEM", 0, AuditAction.UPDATE, fresh_actor, new_value="db_restored")
        db.commit()
    finally:
        db.close()

    return {"detail": "Database restored. A backup of the previous database was saved alongside it on the server."}
