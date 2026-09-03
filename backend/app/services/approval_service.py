import datetime as dt
import json

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.enums import RoleName, ChangeRequestStatus, AuditAction, TransactionType
from app.models.models import ApprovalRule, ChangeRequest, EmploymentEpisode, Employee, OrgAssignment, User, DocumentMeta
from app.services import audit_service

# Fields each transaction type is allowed to change via the ChangeRequest
# flow, and which model they live on. Bank/Statutory/OrgAssignment/
# CostAllocation are already effective-dated, append-only rows (a "change"
# there is a new row, never an overwrite of history) so they're not routed
# through ChangeRequest - only the two entities that genuinely support a
# direct in-place overwrite (Employee identity fields, EmploymentEpisode
# employment fields) need this gate to satisfy blueprint §15's "approved
# data must not be overwritten directly".
CHANGE_REQUEST_TARGETS = {
    "IDENTITY_CHANGE": Employee,
    "EMPLOYMENT_CHANGE": EmploymentEpisode,
}


def current_cost_center_id(db: Session, episode_id: int) -> int | None:
    row = (
        db.query(OrgAssignment)
        .filter(OrgAssignment.episode_id == episode_id, OrgAssignment.effective_to.is_(None))
        .order_by(OrgAssignment.effective_from.desc())
        .first()
    )
    return row.cost_center_id if row else None


def find_approval_rule(db: Session, transaction_type: str, cost_center_id: int | None, employee_category_id: int | None) -> ApprovalRule | None:
    """Most-specific-first match: cost_center+category -> cost_center-only
    -> category-only -> global fallback (cost_center=None, category=None)."""
    candidates = db.query(ApprovalRule).filter(ApprovalRule.transaction_type == transaction_type).all()
    ranked = []
    for rule in candidates:
        cc_match = rule.cost_center_id is None or rule.cost_center_id == cost_center_id
        cat_match = rule.employee_category_id is None or rule.employee_category_id == employee_category_id
        if not (cc_match and cat_match):
            continue
        specificity = (rule.cost_center_id is not None) + (rule.employee_category_id is not None)
        ranked.append((specificity, rule))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked[0][1]


def authorize_approval(db: Session, user: User, episode: EmploymentEpisode, transaction_type: str) -> None:
    if user.role.name == RoleName.HR_ADMIN:
        return
    cost_center_id = current_cost_center_id(db, episode.id)
    rule = find_approval_rule(db, transaction_type, cost_center_id, episode.employee_category_id)
    if rule:
        if rule.approver_user_id is not None:
            if user.id != rule.approver_user_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the assigned approver for this record")
            return
        if user.role.name != rule.approver_role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role {rule.approver_role} to approve this record")
        return
    # No matching rule - fall back to any APPROVER.
    if user.role.name != RoleName.APPROVER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires the Approver role (no approval rule matched)")


def apply_changes(db: Session, episode: EmploymentEpisode, transaction_type: str, changes: dict) -> dict:
    """Applies `changes` (field -> new value) to the model targeted by
    transaction_type, returning the previous values. Used identically by
    the direct-edit path and the change-request-approval path so the two
    can never drift (mirrors sunlease-expms's edit_request_service.apply_changes)."""
    target_model = CHANGE_REQUEST_TARGETS[transaction_type]
    target = episode.employee if target_model is Employee else episode

    previous = {}
    for field, value in changes.items():
        previous[field] = getattr(target, field)
        setattr(target, field, value)
    db.add(target)
    return previous


def create_change_request(db: Session, episode: EmploymentEpisode, transaction_type: str, changes: dict, actor: User) -> ChangeRequest:
    target_model = CHANGE_REQUEST_TARGETS[transaction_type]
    target = episode.employee if target_model is Employee else episode
    previous_values = {field: getattr(target, field) for field in changes}

    request = ChangeRequest(
        episode_id=episode.id,
        transaction_type=transaction_type,
        changes_json=json.dumps(changes, default=str),
        previous_values_json=json.dumps(previous_values, default=str),
        requested_by_id=actor.id,
        status=ChangeRequestStatus.PENDING,
    )
    db.add(request)
    db.flush()
    audit_service.record(db, "CHANGE_REQUEST", request.id, AuditAction.CREATE, actor, new_value=transaction_type)
    return request


def create_document_change_request(db: Session, episode: EmploymentEpisode, document: DocumentMeta, staged: dict, actor: User) -> ChangeRequest:
    """Same shape as create_change_request but for a document replacement:
    the file itself (not a field on Employee/EmploymentEpisode) is what's
    being swapped, so changes/previous_values carry object keys rather
    than field->value pairs - see document_service.stage_replacement."""
    changes = dict(staged, document_meta_id=document.id)
    previous_values = {
        "document_meta_id": document.id,
        "old_object_key": document.object_key,
        "old_file_name": document.file_name,
    }
    request = ChangeRequest(
        episode_id=episode.id,
        transaction_type=TransactionType.DOCUMENT_CHANGE,
        changes_json=json.dumps(changes, default=str),
        previous_values_json=json.dumps(previous_values, default=str),
        requested_by_id=actor.id,
        status=ChangeRequestStatus.PENDING,
    )
    db.add(request)
    db.flush()
    audit_service.record(db, "CHANGE_REQUEST", request.id, AuditAction.CREATE, actor, new_value=TransactionType.DOCUMENT_CHANGE)
    return request


def review_change_request(db: Session, request: ChangeRequest, actor: User, approve: bool, remarks: str | None = None) -> ChangeRequest:
    if request.status != ChangeRequestStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This change request has already been reviewed")

    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == request.episode_id).first()
    authorize_approval(db, actor, episode, request.transaction_type)

    request.reviewed_by_id = actor.id
    request.reviewed_at = dt.datetime.utcnow()
    request.review_remarks = remarks

    if request.transaction_type == TransactionType.DOCUMENT_CHANGE:
        from app.services import document_service  # local import: document_service imports this module too

        staged = json.loads(request.changes_json)
        document = db.query(DocumentMeta).filter(DocumentMeta.id == staged["document_meta_id"]).first()
        if approve:
            if document:
                document_service.apply_staged_replacement(db, document, staged)
            request.status = ChangeRequestStatus.APPROVED
            audit_service.record(db, "CHANGE_REQUEST", request.id, AuditAction.APPROVE, actor, new_value=request.changes_json)
        else:
            document_service.discard_staged_replacement(staged)
            request.status = ChangeRequestStatus.REJECTED
            audit_service.record(db, "CHANGE_REQUEST", request.id, AuditAction.REJECT, actor, new_value=remarks)
        db.add(request)
        return request

    if approve:
        changes = json.loads(request.changes_json)
        apply_changes(db, episode, request.transaction_type, changes)
        request.status = ChangeRequestStatus.APPROVED
        audit_service.record(db, "CHANGE_REQUEST", request.id, AuditAction.APPROVE, actor, new_value=request.changes_json)
    else:
        request.status = ChangeRequestStatus.REJECTED
        audit_service.record(db, "CHANGE_REQUEST", request.id, AuditAction.REJECT, actor, new_value=remarks)

    db.add(request)
    return request
