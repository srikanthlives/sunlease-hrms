import io

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.enums import Permission
from app.models.models import ComplianceRecord, User
from app.schemas.compliance import AggregateSchemeIn, MarkFiledIn
from app.services import compliance_service, permission_service

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"], dependencies=[Depends(get_current_user)])


def _record_dict(r: ComplianceRecord) -> dict:
    return {
        "id": r.id, "scheme": r.scheme, "cost_center_id": r.cost_center_id, "year": r.year, "month": r.month,
        "total_employee_contribution": r.total_employee_contribution,
        "total_employer_contribution": r.total_employer_contribution,
        "employees_covered": r.employees_covered, "status": r.status,
        "challan_reference_number": r.challan_reference_number, "filed_date": r.filed_date, "remarks": r.remarks,
        "created_at": r.created_at, "updated_at": r.updated_at,
    }


@router.get("/records", dependencies=[Depends(require_permission(Permission.COMPLIANCE_VIEW))])
def list_records(
    scheme: str | None = Query(None), cost_center_id: int | None = Query(None),
    year: int | None = Query(None), month: int | None = Query(None),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    query = db.query(ComplianceRecord)
    if scheme is not None:
        query = query.filter(ComplianceRecord.scheme == scheme)
    if cost_center_id is not None:
        query = query.filter(ComplianceRecord.cost_center_id == cost_center_id)
    if year is not None:
        query = query.filter(ComplianceRecord.year == year)
    if month is not None:
        query = query.filter(ComplianceRecord.month == month)
    rows = query.order_by(ComplianceRecord.year.desc(), ComplianceRecord.month.desc(), ComplianceRecord.scheme).all()
    rows = [r for r in rows if permission_service.can_see_cost_center(db, user, r.cost_center_id)]
    return [_record_dict(r) for r in rows]


# Aggregating persists a ComplianceRecord (a write, not just a read), so
# it's gated on COMPLIANCE_FILE rather than COMPLIANCE_VIEW - a judgment
# call per the plan's note ("lean toward COMPLIANCE_FILE since it persists
# a record").
@router.post("/records/{scheme}/aggregate", dependencies=[Depends(require_permission(Permission.COMPLIANCE_FILE))])
def aggregate_scheme(scheme: str, payload: AggregateSchemeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not permission_service.can_see_cost_center(db, user, payload.cost_center_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This Cost Center is outside your scope")
    try:
        record = compliance_service.aggregate_scheme(db, scheme.upper(), payload.cost_center_id, payload.year, payload.month)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(record)
    return _record_dict(record)


@router.post("/records/{record_id}/mark-filed", dependencies=[Depends(require_permission(Permission.COMPLIANCE_FILE))])
def mark_filed(record_id: int, payload: MarkFiledIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        record = compliance_service.mark_filed(
            db, record_id, payload.challan_reference_number, payload.filed_date, payload.remarks, user,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    db.commit()
    db.refresh(record)
    return _record_dict(record)


@router.get("/records/{record_id}/download", dependencies=[Depends(require_permission(Permission.COMPLIANCE_VIEW))])
def download_statement(record_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Downloads a best-effort per-employee contribution statement (xlsx)
    for one ComplianceRecord.

    CAVEAT: this is a best-effort contribution statement only - verify the
    column layout against the current EPFO/ESIC/state PT/LWF portal
    specification before uploading anywhere. It is NOT a certified
    government template.
    """
    record = db.query(ComplianceRecord).filter(ComplianceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compliance record not found")
    if not permission_service.can_see_cost_center(db, user, record.cost_center_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This Cost Center is outside your scope")

    wb = compliance_service.build_scheme_statement_workbook(db, record)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=compliance_{record.scheme}_{record.year}_{record.month}.xlsx"},
    )
