from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import ast
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_admin, require_any
from ..utils.excel import parse_template_components_upload

router = APIRouter(prefix="/templates", tags=["salary-templates"])


@router.get("", response_model=list[schemas.SalaryTemplateOut])
def list_templates(db: Session = Depends(get_db), _=Depends(require_any)):
    return db.query(models.SalaryTemplate).all()


@router.get("/{template_id}", response_model=schemas.SalaryTemplateOut)
def get_template(template_id: int, db: Session = Depends(get_db), _=Depends(require_any)):
    t = db.query(models.SalaryTemplate).get(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.post("", response_model=schemas.SalaryTemplateOut)
def create_template(payload: schemas.SalaryTemplateCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(models.SalaryTemplate).filter_by(template_no=payload.template_no).first():
        raise HTTPException(status_code=400, detail="Template number already exists")
    template = models.SalaryTemplate(
        template_no=payload.template_no, name=payload.name, description=payload.description,
        location=payload.location,
    )
    db.add(template)
    db.flush()
    for comp in payload.components:
        db.add(models.SalaryComponent(template_id=template.id, **comp.model_dump()))
    db.commit()
    db.refresh(template)
    return template


@router.post("/{template_id}/clone", response_model=schemas.SalaryTemplateOut)
def clone_template(template_id: int, payload: schemas.TemplateCloneRequest, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Duplicate a template (and all its components) under a new template number/name - handy for
    creating a location-specific variant or a starting point for a new role without rebuilding
    every component from scratch."""
    source = db.query(models.SalaryTemplate).get(template_id)
    if not source:
        raise HTTPException(status_code=404, detail="Template not found")
    if db.query(models.SalaryTemplate).filter_by(template_no=payload.template_no).first():
        raise HTTPException(status_code=400, detail="Template number already exists")

    clone = models.SalaryTemplate(
        template_no=payload.template_no,
        name=payload.name,
        description=source.description,
        location=payload.location if payload.location is not None else source.location,
    )
    db.add(clone)
    db.flush()

    for comp in source.components:
        db.add(models.SalaryComponent(
            template_id=clone.id, code=comp.code, name=comp.name, component_type=comp.component_type,
            calculation_type=comp.calculation_type, value=comp.value, formula=comp.formula,
            is_variable=comp.is_variable, default_value=comp.default_value,
            prorate_by_attendance=comp.prorate_by_attendance, sequence=comp.sequence, is_active=comp.is_active,
        ))
    db.commit()
    db.refresh(clone)
    return clone


@router.put("/{template_id}", response_model=schemas.SalaryTemplateOut)
def update_template(template_id: int, payload: schemas.SalaryTemplateUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    template = db.query(models.SalaryTemplate).get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if payload.name is not None:
        template.name = payload.name
    if payload.description is not None:
        template.description = payload.description
    if payload.location is not None:
        template.location = payload.location or None
    if payload.is_active is not None:
        template.is_active = payload.is_active

    if payload.components is not None:
        # Full replace of the component set for this template.
        db.query(models.SalaryComponent).filter_by(template_id=template.id).delete()
        db.flush()
        for comp in payload.components:
            db.add(models.SalaryComponent(template_id=template.id, **comp.model_dump()))

    db.commit()
    db.refresh(template)
    return template


@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    template = db.query(models.SalaryTemplate).get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    in_use = db.query(models.Employee).filter_by(template_id=template_id).count()
    if in_use:
        raise HTTPException(status_code=400, detail=f"Template is assigned to {in_use} employee(s); reassign them first.")
    db.delete(template)
    db.commit()
    return {"detail": "Template deleted"}


_VALID_COMPONENT_TYPES = {c.value for c in models.ComponentType}
_VALID_CALC_TYPES = {c.value for c in models.CalculationType}
_TRUE_STRINGS = {"true", "yes", "y", "1"}
_FALSE_STRINGS = {"false", "no", "n", "0", ""}


def _validate_component_row(row: dict, row_num: int, seen_codes: set) -> list[str]:
    """Validate one parsed Excel row. Returns a list of error strings (empty if the row is valid)."""
    errors = []
    prefix = f"Row {row_num}"

    code = (row.get("code") or "").strip().upper()
    if not code:
        errors.append(f"{prefix}: 'code' is required")
    elif code in seen_codes:
        errors.append(f"{prefix}: duplicate component code '{code}' in this file")
    else:
        seen_codes.add(code)

    if not (row.get("name") or "").strip():
        errors.append(f"{prefix}: 'name' is required")

    component_type = (row.get("component_type") or "").strip().lower()
    if component_type not in _VALID_COMPONENT_TYPES:
        errors.append(f"{prefix}: invalid component_type '{row.get('component_type')}' (expected one of {sorted(_VALID_COMPONENT_TYPES)})")

    calculation_type = (row.get("calculation_type") or "").strip().lower()
    if calculation_type not in _VALID_CALC_TYPES:
        errors.append(f"{prefix}: invalid calculation_type '{row.get('calculation_type')}' (expected one of {sorted(_VALID_CALC_TYPES)})")

    for field in ("value", "default_value", "sequence"):
        raw = row.get(field)
        if raw not in (None, ""):
            try:
                float(raw)
            except (TypeError, ValueError):
                errors.append(f"{prefix}: '{field}' must be a number, got '{raw}'")

    for field in ("is_variable", "prorate_by_attendance"):
        raw = str(row.get(field, "")).strip().lower()
        if raw not in _TRUE_STRINGS and raw not in _FALSE_STRINGS:
            errors.append(f"{prefix}: '{field}' must be yes/no (or true/false), got '{row.get(field)}'")

    if calculation_type in ("formula", "percentage"):
        formula = (row.get("formula") or "").strip()
        if not formula:
            errors.append(f"{prefix}: 'formula' is required when calculation_type is '{calculation_type}'")
        else:
            try:
                ast.parse(formula, mode="eval")
            except SyntaxError as e:
                errors.append(f"{prefix}: 'formula' has a syntax error - {e.msg}")

    return errors


@router.post("/{template_id}/components/upload", response_model=schemas.TemplateComponentsUploadResult)
async def upload_template_components(
    template_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(require_admin),
):
    """
    Bulk-replace a template's components from an Excel file. Columns: code, name,
    component_type (earning/deduction/employer_contribution/reference), calculation_type
    (fixed/percentage/formula), value, formula, is_variable (yes/no), default_value,
    prorate_by_attendance (yes/no), sequence.

    Every row is validated BEFORE anything is applied - if any row has a problem, the whole
    upload is rejected with the full list of row-level errors so nothing is left half-applied.
    """
    template = db.query(models.SalaryTemplate).get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    content = await file.read()
    try:
        rows = parse_template_components_upload(content)
    except ValueError as e:
        return schemas.TemplateComponentsUploadResult(success=False, errors=[str(e)])

    if not rows:
        return schemas.TemplateComponentsUploadResult(success=False, errors=["No data rows found in the file."])

    errors = []
    seen_codes: set = set()
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        errors.extend(_validate_component_row(row, i, seen_codes))

    if errors:
        return schemas.TemplateComponentsUploadResult(success=False, errors=errors)

    # All rows valid - replace the template's components.
    db.query(models.SalaryComponent).filter_by(template_id=template.id).delete()
    db.flush()
    for i, row in enumerate(rows):
        db.add(models.SalaryComponent(
            template_id=template.id,
            code=(row["code"] or "").strip().upper(),
            name=(row["name"] or "").strip(),
            component_type=(row["component_type"] or "").strip().lower(),
            calculation_type=(row["calculation_type"] or "").strip().lower(),
            value=float(row["value"]) if row.get("value") not in (None, "") else 0,
            formula=(row.get("formula") or "").strip() or None,
            is_variable=str(row.get("is_variable", "")).strip().lower() in _TRUE_STRINGS,
            default_value=float(row["default_value"]) if row.get("default_value") not in (None, "") else 0,
            prorate_by_attendance=str(row.get("prorate_by_attendance", "")).strip().lower() in _TRUE_STRINGS,
            sequence=int(float(row["sequence"])) if row.get("sequence") not in (None, "") else i + 1,
        ))
    db.commit()

    return schemas.TemplateComponentsUploadResult(success=True, applied=len(rows), errors=[])
