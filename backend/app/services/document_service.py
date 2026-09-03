import os
import re
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import (
    DocumentMeta, DocumentRequirement, DocumentType,
    EmploymentEpisode, User,
)
from app.services import approval_service


def _slug(value: str) -> str:
    """Filesystem-safe slug: lowercase, alnum/dash/underscore only."""
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return value or "unnamed"


def resolve_required_documents(db: Session, episode: EmploymentEpisode) -> list[dict]:
    """Matches DocumentRequirement rules against the episode's Employee
    Type / Category / Designation (blueprint §14, extended per the admin's
    Document Configuration screen). A rule applies if every dimension it
    constrains matches (null dimensions are wildcards). When more than one
    matching rule targets the same DocumentType, the highest-priority
    rule's is_mandatory wins - Employee Type (weight 3) > Employee
    Category (weight 2) > Designation (weight 1); an unscoped/global rule
    has weight 0 and loses to any more specific match."""
    rules = (
        db.query(DocumentRequirement)
        .filter(DocumentRequirement.is_active.is_(True))
        .all()
    )

    best_by_type: dict[int, tuple[int, DocumentRequirement]] = {}
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
        current = best_by_type.get(rule.document_type_id)
        if current is None or weight > current[0]:
            best_by_type[rule.document_type_id] = (weight, rule)

    uploaded_by_type = {d.document_type_id: d for d in episode.documents if d.document_type_id}

    result = []
    for document_type_id, (_, rule) in best_by_type.items():
        doc = uploaded_by_type.get(document_type_id)
        result.append({
            "document_type_id": document_type_id,
            "document_type_name": rule.document_type.name,
            "is_mandatory": rule.is_mandatory,
            "uploaded": doc is not None,
            "document_meta_id": doc.id if doc else None,
            "file_name": doc.file_name if doc else None,
            "verification_status": doc.verification_status if doc else None,
        })
    result.sort(key=lambda r: r["document_type_name"])
    return result


def _employee_upload_dir(db: Session, episode: EmploymentEpisode) -> str:
    company_name = "Unassigned"
    cc_id = approval_service.current_cost_center_id(db, episode.id)
    if cc_id:
        from app.models.models import CostCenter
        cc = db.query(CostCenter).filter(CostCenter.id == cc_id).first()
        if cc and cc.company:
            company_name = cc.company.name
    return os.path.join(settings.UPLOAD_DIR, _slug(company_name), episode.employee_number)


def save_upload(db: Session, episode: EmploymentEpisode, document_type_id: int, upload_file: UploadFile, actor: User) -> DocumentMeta:
    doc_type = db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
    if not doc_type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown document type")

    ext = os.path.splitext(upload_file.filename or "")[1]
    target_dir = _employee_upload_dir(db, episode)
    os.makedirs(target_dir, exist_ok=True)
    stored_name = f"{_slug(doc_type.name)}{ext}"
    full_path = os.path.join(target_dir, stored_name)

    content = upload_file.file.read()
    with open(full_path, "wb") as f:
        f.write(content)

    object_key = os.path.relpath(full_path, settings.UPLOAD_DIR)

    record = db.query(DocumentMeta).filter(
        DocumentMeta.episode_id == episode.id, DocumentMeta.document_type_id == document_type_id,
    ).first()
    if record:
        record.version = (record.version or 1) + 1
        record.verification_status = "PENDING"
    else:
        record = DocumentMeta(episode_id=episode.id, document_type_id=document_type_id)
        db.add(record)

    record.document_type = doc_type.name
    record.file_name = upload_file.filename
    record.object_key = object_key
    record.file_size = len(content)
    record.mime_type = upload_file.content_type
    record.uploaded_by_id = actor.id
    return record


def resolve_file_path(document: DocumentMeta) -> str:
    return os.path.join(settings.UPLOAD_DIR, document.object_key)


def stage_replacement(db: Session, episode: EmploymentEpisode, document_type_id: int, upload_file: UploadFile) -> dict:
    """Writes a replacement upload to disk under a distinct (non-clobbering)
    name, without touching the existing DocumentMeta row - used when a
    replacement for an already-uploaded document needs approval first
    (blueprint §15 applied to Documents). The staged file is only made the
    document of record - and the old file only deleted - once the
    resulting ChangeRequest is approved (approval_service.review_change_request)."""
    doc_type = db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
    if not doc_type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown document type")

    ext = os.path.splitext(upload_file.filename or "")[1]
    target_dir = _employee_upload_dir(db, episode)
    os.makedirs(target_dir, exist_ok=True)
    stored_name = f"{_slug(doc_type.name)}-pending-{uuid4().hex[:8]}{ext}"
    full_path = os.path.join(target_dir, stored_name)

    content = upload_file.file.read()
    with open(full_path, "wb") as f:
        f.write(content)

    return {
        "document_type_id": document_type_id,
        "new_object_key": os.path.relpath(full_path, settings.UPLOAD_DIR),
        "new_file_name": upload_file.filename,
        "new_file_size": len(content),
        "new_mime_type": upload_file.content_type,
    }


def apply_staged_replacement(db: Session, record: DocumentMeta, staged: dict) -> None:
    """Approval-time: swap the record over to the staged file and delete
    the old one - old and new never coexist on disk past this point."""
    old_path = resolve_file_path(record)
    if os.path.exists(old_path):
        os.remove(old_path)
    record.file_name = staged["new_file_name"]
    record.object_key = staged["new_object_key"]
    record.file_size = staged["new_file_size"]
    record.mime_type = staged["new_mime_type"]
    record.version = (record.version or 1) + 1
    record.verification_status = "PENDING"
    db.add(record)


def discard_staged_replacement(staged: dict) -> None:
    """Rejection-time: drop the staged file: the old document stays as
    the document of record."""
    path = os.path.join(settings.UPLOAD_DIR, staged["new_object_key"])
    if os.path.exists(path):
        os.remove(path)


def save_employee_photo(db: Session, episode: EmploymentEpisode, upload_file: UploadFile) -> str:
    """Employee photo lives on Basic Details (Personal Information), not
    in the generic Documents list - stored the same way as other
    documents (company/employee-number folder, renamed to "photo") but
    tracked on Employee.photo_object_key rather than a DocumentMeta row."""
    ext = os.path.splitext(upload_file.filename or "")[1] or ".jpg"
    target_dir = _employee_upload_dir(db, episode)
    os.makedirs(target_dir, exist_ok=True)
    full_path = os.path.join(target_dir, f"photo{ext}")

    content = upload_file.file.read()
    with open(full_path, "wb") as f:
        f.write(content)

    employee = episode.employee
    employee.photo_object_key = os.path.relpath(full_path, settings.UPLOAD_DIR)
    db.add(employee)
    return employee.photo_object_key


def resolve_employee_photo_path(employee) -> str | None:
    if not employee.photo_object_key:
        return None
    return os.path.join(settings.UPLOAD_DIR, employee.photo_object_key)
