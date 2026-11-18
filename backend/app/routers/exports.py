"""Configurable Excel export of the Employees and Candidates lists.

The wizard that drives this is frontend/src/components/ExportWizard.jsx:
pick a saved pattern (or start fresh) -> choose and order columns -> filter
the rows -> preview -> download. Preview and download go through the same
services/export_service.build_rows, so the preview is not an approximation
of the file; it is the file's first page.
"""
import io

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.enums import AuditAction, Permission
from app.models.models import User
from app.schemas.exports import DocumentBundleIn, DocumentSelectionIn, ExportSpecIn, ExportTemplateIn
from app.services import audit_service, document_bundle_service, export_service

router = APIRouter(prefix="/api/v1/exports", tags=["exports"], dependencies=[Depends(get_current_user)])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _require_entity_permission(entity: str, db: Session, user: User) -> None:
    """Exporting a list needs the same permission as viewing it - the export
    is a different rendering of data the caller can already see, never a way
    to reach data they cannot."""
    from app.services import permission_service

    code = Permission.EMPLOYEE_VIEW if entity == export_service.EMPLOYEE else Permission.RECRUITMENT_VIEW
    if not permission_service.has_permission(db, user, code):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not allowed to view this data")


@router.get("/columns")
def list_columns(entity: str = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The column catalog the wizard offers, plus the default selection a
    fresh pattern starts from. Sensitive employee columns are absent for a
    caller without employee.sensitive.view."""
    entity = export_service.check_entity(entity)
    _require_entity_permission(entity, db, user)
    return {
        "entity": entity,
        "columns": export_service.columns_for(db, user, entity),
        "default_columns": export_service.DEFAULT_COLUMNS[entity],
        "filter_keys": list(export_service.FILTER_KEYS[entity]),
        "preview_rows": export_service.PREVIEW_ROWS,
    }


@router.post("/preview")
def preview_export(payload: ExportSpecIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The first page of the exact file the same spec would download, plus
    the full row count behind it - so an empty or far-too-large export is
    visible before anyone waits for a download."""
    entity = export_service.check_entity(payload.entity)
    _require_entity_permission(entity, db, user)
    columns, rows = export_service.build_rows(db, user, entity, payload.model_dump())
    shown = rows[:export_service.PREVIEW_ROWS]
    return {
        "columns": [{"key": c["key"], "label": c["label"], "sensitive": c["sensitive"]} for c in columns],
        "rows": [[row.get(c["key"]) for c in columns] for row in shown],
        "total": len(rows),
        "shown": len(shown),
    }


@router.post("/download")
def download_export(payload: ExportSpecIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entity = export_service.check_entity(payload.entity)
    _require_entity_permission(entity, db, user)
    workbook, row_count = export_service.build_workbook(db, user, entity, payload.model_dump())
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    # An export leaves the system with real data in it, so it is audited
    # like any other action - who exported which columns, and how many rows.
    audit_service.record(
        db, "EXPORT", user.id, AuditAction.UPDATE, user,
        new_value=f"exported {row_count} {entity.lower()} row(s) as xlsx; columns: {', '.join(payload.columns)}",
    )
    db.commit()

    name = "employees" if entity == export_service.EMPLOYEE else "candidates"
    return StreamingResponse(
        buffer, media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename=hrms_{name}_export.xlsx"},
    )


# ---------------------------------------------------------------------------
# Saved patterns
# ---------------------------------------------------------------------------

@router.get("/templates")
def list_templates(entity: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Your own patterns plus any shared one."""
    return [export_service.template_dict(t, user) for t in export_service.visible_templates(db, user, entity)]


@router.post("/templates")
def create_template(payload: ExportTemplateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entity = export_service.check_entity(payload.entity)
    _require_entity_permission(entity, db, user)
    template = export_service.save_template(db, user, payload.model_dump())
    audit_service.record(db, "EXPORT_TEMPLATE", template.id, AuditAction.CREATE, user, new_value=f"{template.entity}: {template.name}")
    db.commit()
    return export_service.template_dict(template, user)


@router.put("/templates/{template_id}")
def update_template(template_id: int, payload: ExportTemplateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = export_service.get_own_template(db, user, template_id)
    entity = export_service.check_entity(payload.entity)
    _require_entity_permission(entity, db, user)
    template = export_service.save_template(db, user, payload.model_dump(), template=existing)
    audit_service.record(db, "EXPORT_TEMPLATE", template.id, AuditAction.UPDATE, user, new_value=f"{template.entity}: {template.name}")
    db.commit()
    return export_service.template_dict(template, user)


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """A genuine delete: a saved pattern is a convenience, not history (same
    reasoning as an ad-hoc pay entry), so there is nothing to preserve."""
    template = export_service.get_own_template(db, user, template_id)
    audit_service.record(db, "EXPORT_TEMPLATE", template.id, AuditAction.UPDATE, user, old_value=f"{template.entity}: {template.name}")
    db.delete(template)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Bulk document download
# ---------------------------------------------------------------------------

def _require_document_permission(entity: str, db: Session, user: User) -> None:
    """Downloading someone's documents in bulk needs the same permission as
    opening one of them on their profile - employee.documents.view, or
    recruitment.view for a candidate (which is what the per-candidate
    document download already requires)."""
    from app.services import permission_service

    code = (Permission.EMPLOYEE_DOCUMENTS_VIEW if entity == document_bundle_service.EMPLOYEE
            else Permission.RECRUITMENT_VIEW)
    if not permission_service.has_permission(db, user, code):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not allowed to view these documents")


@router.post("/documents/preflight")
def documents_preflight(payload: DocumentSelectionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Every document type any of the selected people has on file, each with
    an uploaded/missing count, so the dialog's document multi-select offers
    real choices ("Aadhaar - 11 of 12") instead of the whole master list."""
    entity = document_bundle_service.check_entity(payload.entity)
    _require_document_permission(entity, db, user)
    return document_bundle_service.preflight(db, user, entity, payload.ids)


@router.post("/documents/download")
def download_documents(payload: DocumentBundleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """One merged PDF per selected person, zipped when there is more than
    one. The counts and anything left out are echoed in response headers
    (X-Bundle-*), since a file download body has nowhere else to say so."""
    entity = document_bundle_service.check_entity(payload.entity)
    _require_document_permission(entity, db, user)
    bundle = document_bundle_service.build_bundle(db, user, entity, payload.ids, payload.document_type_ids)

    # Documents leaving the system in bulk is worth a trail of its own.
    audit_service.record(
        db, "DOCUMENT_BULK_DOWNLOAD", user.id, AuditAction.UPDATE, user,
        new_value=f"downloaded {bundle['documents_included']} document(s) for {bundle['people_included']} "
                  f"{entity.lower()}(s) as {bundle['media_type']}; "
                  f"document types: {', '.join(str(i) for i in payload.document_type_ids)}"
                  + (f"; {len(bundle['skipped'])} left out" if bundle["skipped"] else ""),
    )
    db.commit()

    return Response(
        content=bundle["content"], media_type=bundle["media_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{bundle["filename"]}"',
            "X-Bundle-People": str(bundle["people_included"]),
            "X-Bundle-Documents": str(bundle["documents_included"]),
            "X-Bundle-Skipped": str(len(bundle["skipped"])),
            # So the browser can read the three headers above off the response.
            "Access-Control-Expose-Headers": "X-Bundle-People, X-Bundle-Documents, X-Bundle-Skipped, Content-Disposition",
        },
    )
