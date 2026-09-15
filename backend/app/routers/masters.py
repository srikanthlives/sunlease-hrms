from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_hr_admin
from app.db.session import get_db
from app.models.enums import Permission
from app.models.models import (
    Company, CostCenter, Project, Department, EmployeeCategory,
    WorkLocation, Designation, EmployeeType, DocumentType, DocumentRequirement,
    DrivingLicenceRequirement,
    Role, RolePermission, UserCostCenterScope, ApprovalRule, User,
    OrgAssignment, CostAllocation, EmploymentEpisode, HolidayCalendar,
    PayrollRun, PayslipCostSplit, ComplianceRecord, LeaveEligibilityRule,
    DesignationCriteria, Candidate,
)
from app.schemas.masters import (
    CompanyIn, CompanyOut, CostCenterIn, CostCenterOut,
    ProjectIn, ProjectOut, DepartmentIn, DepartmentOut,
    EmployeeCategoryIn, EmployeeCategoryOut,
    WorkLocationIn, WorkLocationOut, DesignationIn, DesignationOut,
    EmployeeTypeIn, EmployeeTypeOut,
    DocumentTypeIn, DocumentTypeOut, DocumentRequirementIn, DocumentRequirementOut,
    DrivingLicenceRequirementIn, DrivingLicenceRequirementOut,
    RolePermissionsUpdate, CostCenterScopeUpdate, ApprovalRuleIn, ApprovalRuleOut,
)

router = APIRouter(prefix="/api/v1", tags=["masters"])


def _delete_or_deactivate(db: Session, obj, usage_checks: list) -> dict:
    """Physically deletes `obj` if nothing references it yet; otherwise
    falls back to the existing soft-deactivate (is_active=False) so rows
    already pointing at it keep working. `usage_checks` is a list of
    (Model, column) pairs to check for a referencing row."""
    in_use = any(
        db.query(model).filter(column == obj.id).first() is not None
        for model, column in usage_checks
    )
    if in_use:
        obj.is_active = False
        db.add(obj)
        db.commit()
        return {"ok": True, "deleted": False}
    db.delete(obj)
    db.commit()
    return {"ok": True, "deleted": True}

# Organization setup (Company/Cost Center/Project/Department/Employee
# Category) is the org-model foundation (blueprint §2, §13) - HR Admin
# controlled, read-open to any authenticated user (they need it to build
# the Employee Wizard's dropdowns).


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(Company).filter(Company.is_active.is_(True)).all()


@router.post("/companies", response_model=CompanyOut, dependencies=[Depends(require_hr_admin)])
def create_company(payload: CompanyIn, db: Session = Depends(get_db)):
    if db.query(Company).filter(Company.name == payload.name).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Company already exists")
    if db.query(Company).filter(Company.code == payload.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Company code already in use")
    obj = Company(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/companies/{company_id}", response_model=CompanyOut, dependencies=[Depends(require_hr_admin)])
def update_company(company_id: int, payload: CompanyIn, db: Session = Depends(get_db)):
    obj = db.query(Company).filter(Company.id == company_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    dupe = db.query(Company).filter(Company.name == payload.name, Company.id != company_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Company already exists")
    code_dupe = db.query(Company).filter(Company.code == payload.code, Company.id != company_id).first()
    if code_dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Company code already in use")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/companies/{company_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_company(company_id: int, db: Session = Depends(get_db)):
    obj = db.query(Company).filter(Company.id == company_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    obj.is_active = False  # never physically deleted (blueprint §21)
    db.add(obj)
    db.commit()
    return {"ok": True}


@router.get("/cost-centers", response_model=list[CostCenterOut])
def list_cost_centers(include_inactive: bool = False, db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = db.query(CostCenter)
    if not include_inactive:
        query = query.filter(CostCenter.is_active.is_(True))
    return query.all()


@router.post("/cost-centers/{cost_center_id}/activate", dependencies=[Depends(require_hr_admin)])
def activate_cost_center(cost_center_id: int, db: Session = Depends(get_db)):
    obj = db.query(CostCenter).filter(CostCenter.id == cost_center_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cost Center not found")
    obj.is_active = True
    db.add(obj)
    db.commit()
    return {"ok": True}


@router.post("/cost-centers", response_model=CostCenterOut, dependencies=[Depends(require_hr_admin)])
def create_cost_center(payload: CostCenterIn, db: Session = Depends(get_db)):
    if db.query(CostCenter).filter(CostCenter.code == payload.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cost Center code already exists")
    obj = CostCenter(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/cost-centers/{cost_center_id}", response_model=CostCenterOut, dependencies=[Depends(require_hr_admin)])
def update_cost_center(cost_center_id: int, payload: CostCenterIn, db: Session = Depends(get_db)):
    obj = db.query(CostCenter).filter(CostCenter.id == cost_center_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cost Center not found")
    dupe = db.query(CostCenter).filter(CostCenter.code == payload.code, CostCenter.id != cost_center_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cost Center code already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/cost-centers/{cost_center_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_cost_center(cost_center_id: int, db: Session = Depends(get_db)):
    obj = db.query(CostCenter).filter(CostCenter.id == cost_center_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cost Center not found")
    return _delete_or_deactivate(db, obj, [
        (OrgAssignment, OrgAssignment.cost_center_id), (CostAllocation, CostAllocation.cost_center_id),
        (Project, Project.cost_center_id),
        (UserCostCenterScope, UserCostCenterScope.cost_center_id), (ApprovalRule, ApprovalRule.cost_center_id),
        (HolidayCalendar, HolidayCalendar.cost_center_id), (PayrollRun, PayrollRun.cost_center_id),
        (PayslipCostSplit, PayslipCostSplit.cost_center_id), (ComplianceRecord, ComplianceRecord.cost_center_id),
        (LeaveEligibilityRule, LeaveEligibilityRule.cost_center_id),
    ])


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(include_inactive: bool = False, db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = db.query(Project)
    if not include_inactive:
        query = query.filter(Project.is_active.is_(True))
    return query.all()


@router.post("/projects/{project_id}/activate", dependencies=[Depends(require_hr_admin)])
def activate_project(project_id: int, db: Session = Depends(get_db)):
    obj = db.query(Project).filter(Project.id == project_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    obj.is_active = True
    db.add(obj)
    db.commit()
    return {"ok": True}


@router.post("/projects", response_model=ProjectOut, dependencies=[Depends(require_hr_admin)])
def create_project(payload: ProjectIn, db: Session = Depends(get_db)):
    if db.query(Project).filter(Project.code == payload.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Project code already exists")
    obj = Project(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/projects/{project_id}", response_model=ProjectOut, dependencies=[Depends(require_hr_admin)])
def update_project(project_id: int, payload: ProjectIn, db: Session = Depends(get_db)):
    obj = db.query(Project).filter(Project.id == project_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    dupe = db.query(Project).filter(Project.code == payload.code, Project.id != project_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Project code already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/projects/{project_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_project(project_id: int, db: Session = Depends(get_db)):
    obj = db.query(Project).filter(Project.id == project_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return _delete_or_deactivate(db, obj, [
        (WorkLocation, WorkLocation.project_id), (CostAllocation, CostAllocation.project_id),
        (OrgAssignment, OrgAssignment.project_id), (PayslipCostSplit, PayslipCostSplit.project_id),
    ])


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(include_inactive: bool = False, db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = db.query(Department)
    if not include_inactive:
        query = query.filter(Department.is_active.is_(True))
    return query.all()


@router.post("/departments/{department_id}/activate", dependencies=[Depends(require_hr_admin)])
def activate_department(department_id: int, db: Session = Depends(get_db)):
    obj = db.query(Department).filter(Department.id == department_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    obj.is_active = True
    db.add(obj)
    db.commit()
    return {"ok": True}


@router.post("/departments", response_model=DepartmentOut, dependencies=[Depends(require_hr_admin)])
def create_department(payload: DepartmentIn, db: Session = Depends(get_db)):
    if db.query(Department).filter(Department.code == payload.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Department code already exists")
    obj = Department(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/departments/{department_id}", response_model=DepartmentOut, dependencies=[Depends(require_hr_admin)])
def update_department(department_id: int, payload: DepartmentIn, db: Session = Depends(get_db)):
    obj = db.query(Department).filter(Department.id == department_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    dupe = db.query(Department).filter(Department.code == payload.code, Department.id != department_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Department code already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/departments/{department_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_department(department_id: int, db: Session = Depends(get_db)):
    obj = db.query(Department).filter(Department.id == department_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    return _delete_or_deactivate(db, obj, [(OrgAssignment, OrgAssignment.department_id)])


@router.get("/employee-categories", response_model=list[EmployeeCategoryOut])
def list_categories(include_inactive: bool = False, db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = db.query(EmployeeCategory)
    if not include_inactive:
        query = query.filter(EmployeeCategory.is_active.is_(True))
    return query.all()


@router.post("/employee-categories/{category_id}/activate", dependencies=[Depends(require_hr_admin)])
def activate_category(category_id: int, db: Session = Depends(get_db)):
    obj = db.query(EmployeeCategory).filter(EmployeeCategory.id == category_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    obj.is_active = True
    db.add(obj)
    db.commit()
    return {"ok": True}


@router.post("/employee-categories", response_model=EmployeeCategoryOut, dependencies=[Depends(require_hr_admin)])
def create_category(payload: EmployeeCategoryIn, db: Session = Depends(get_db)):
    if db.query(EmployeeCategory).filter(EmployeeCategory.name == payload.name).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Category already exists")
    obj = EmployeeCategory(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/employee-categories/{category_id}", response_model=EmployeeCategoryOut, dependencies=[Depends(require_hr_admin)])
def update_category(category_id: int, payload: EmployeeCategoryIn, db: Session = Depends(get_db)):
    obj = db.query(EmployeeCategory).filter(EmployeeCategory.id == category_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    dupe = db.query(EmployeeCategory).filter(EmployeeCategory.name == payload.name, EmployeeCategory.id != category_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Category already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/employee-categories/{category_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_category(category_id: int, db: Session = Depends(get_db)):
    obj = db.query(EmployeeCategory).filter(EmployeeCategory.id == category_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return _delete_or_deactivate(db, obj, [
        (EmploymentEpisode, EmploymentEpisode.employee_category_id), (ApprovalRule, ApprovalRule.employee_category_id),
        (DocumentRequirement, DocumentRequirement.employee_category_id),
        (LeaveEligibilityRule, LeaveEligibilityRule.employee_category_id),
        (Designation, Designation.employee_category_id), (Candidate, Candidate.applied_employee_category_id),
    ])


# Work Locations (linked to a Project)
@router.get("/work-locations", response_model=list[WorkLocationOut])
def list_work_locations(include_inactive: bool = False, db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = db.query(WorkLocation)
    if not include_inactive:
        query = query.filter(WorkLocation.is_active.is_(True))
    return query.all()


@router.post("/work-locations/{work_location_id}/activate", dependencies=[Depends(require_hr_admin)])
def activate_work_location(work_location_id: int, db: Session = Depends(get_db)):
    obj = db.query(WorkLocation).filter(WorkLocation.id == work_location_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work Location not found")
    obj.is_active = True
    db.add(obj)
    db.commit()
    return {"ok": True}


@router.post("/work-locations", response_model=WorkLocationOut, dependencies=[Depends(require_hr_admin)])
def create_work_location(payload: WorkLocationIn, db: Session = Depends(get_db)):
    if db.query(WorkLocation).filter(WorkLocation.code == payload.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Work Location code already exists")
    obj = WorkLocation(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/work-locations/{work_location_id}", response_model=WorkLocationOut, dependencies=[Depends(require_hr_admin)])
def update_work_location(work_location_id: int, payload: WorkLocationIn, db: Session = Depends(get_db)):
    obj = db.query(WorkLocation).filter(WorkLocation.id == work_location_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work Location not found")
    dupe = db.query(WorkLocation).filter(WorkLocation.code == payload.code, WorkLocation.id != work_location_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Work Location code already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/work-locations/{work_location_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_work_location(work_location_id: int, db: Session = Depends(get_db)):
    obj = db.query(WorkLocation).filter(WorkLocation.id == work_location_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work Location not found")
    return _delete_or_deactivate(db, obj, [(EmploymentEpisode, EmploymentEpisode.work_location_id)])


# Designations
@router.get("/designations", response_model=list[DesignationOut])
def list_designations(include_inactive: bool = False, db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = db.query(Designation)
    if not include_inactive:
        query = query.filter(Designation.is_active.is_(True))
    return query.all()


@router.post("/designations/{designation_id}/activate", dependencies=[Depends(require_hr_admin)])
def activate_designation(designation_id: int, db: Session = Depends(get_db)):
    obj = db.query(Designation).filter(Designation.id == designation_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Designation not found")
    obj.is_active = True
    db.add(obj)
    db.commit()
    return {"ok": True}


@router.post("/designations", response_model=DesignationOut, dependencies=[Depends(require_hr_admin)])
def create_designation(payload: DesignationIn, db: Session = Depends(get_db)):
    if db.query(Designation).filter(Designation.name == payload.name).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Designation already exists")
    obj = Designation(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/designations/{designation_id}", response_model=DesignationOut, dependencies=[Depends(require_hr_admin)])
def update_designation(designation_id: int, payload: DesignationIn, db: Session = Depends(get_db)):
    obj = db.query(Designation).filter(Designation.id == designation_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Designation not found")
    dupe = db.query(Designation).filter(Designation.name == payload.name, Designation.id != designation_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Designation already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/designations/{designation_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_designation(designation_id: int, db: Session = Depends(get_db)):
    obj = db.query(Designation).filter(Designation.id == designation_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Designation not found")
    return _delete_or_deactivate(db, obj, [
        (EmploymentEpisode, EmploymentEpisode.designation_id), (DocumentRequirement, DocumentRequirement.designation_id),
        (DrivingLicenceRequirement, DrivingLicenceRequirement.designation_id),
        (DesignationCriteria, DesignationCriteria.designation_id), (Candidate, Candidate.applied_designation_id),
    ])


# Employee Types (Employment Type master)
@router.get("/employee-types", response_model=list[EmployeeTypeOut])
def list_employee_types(include_inactive: bool = False, db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = db.query(EmployeeType)
    if not include_inactive:
        query = query.filter(EmployeeType.is_active.is_(True))
    return query.all()


@router.post("/employee-types/{employee_type_id}/activate", dependencies=[Depends(require_hr_admin)])
def activate_employee_type(employee_type_id: int, db: Session = Depends(get_db)):
    obj = db.query(EmployeeType).filter(EmployeeType.id == employee_type_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee Type not found")
    obj.is_active = True
    db.add(obj)
    db.commit()
    return {"ok": True}


@router.post("/employee-types", response_model=EmployeeTypeOut, dependencies=[Depends(require_hr_admin)])
def create_employee_type(payload: EmployeeTypeIn, db: Session = Depends(get_db)):
    if db.query(EmployeeType).filter(EmployeeType.name == payload.name).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Employee Type already exists")
    obj = EmployeeType(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/employee-types/{employee_type_id}", response_model=EmployeeTypeOut, dependencies=[Depends(require_hr_admin)])
def update_employee_type(employee_type_id: int, payload: EmployeeTypeIn, db: Session = Depends(get_db)):
    obj = db.query(EmployeeType).filter(EmployeeType.id == employee_type_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee Type not found")
    dupe = db.query(EmployeeType).filter(EmployeeType.name == payload.name, EmployeeType.id != employee_type_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Employee Type already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/employee-types/{employee_type_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_employee_type(employee_type_id: int, db: Session = Depends(get_db)):
    obj = db.query(EmployeeType).filter(EmployeeType.id == employee_type_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee Type not found")
    return _delete_or_deactivate(db, obj, [
        (EmploymentEpisode, EmploymentEpisode.employment_type_id), (DocumentRequirement, DocumentRequirement.employee_type_id),
    ])


# ---------------------------------------------------------------------------
# Document configuration (blueprint §14) - HR Admin only for writes; reads
# open to any authenticated user (the wizard's Documents step needs them).
# ---------------------------------------------------------------------------

@router.get("/document-types", response_model=list[DocumentTypeOut])
def list_document_types(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(DocumentType).filter(DocumentType.is_active.is_(True)).all()


@router.post("/document-types", response_model=DocumentTypeOut, dependencies=[Depends(require_hr_admin)])
def create_document_type(payload: DocumentTypeIn, db: Session = Depends(get_db)):
    if db.query(DocumentType).filter(DocumentType.name == payload.name).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Document Type already exists")
    obj = DocumentType(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/document-types/{document_type_id}", response_model=DocumentTypeOut, dependencies=[Depends(require_hr_admin)])
def update_document_type(document_type_id: int, payload: DocumentTypeIn, db: Session = Depends(get_db)):
    obj = db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document Type not found")
    dupe = db.query(DocumentType).filter(DocumentType.name == payload.name, DocumentType.id != document_type_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Document Type already exists")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/document-types/{document_type_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_document_type(document_type_id: int, db: Session = Depends(get_db)):
    obj = db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document Type not found")
    obj.is_active = False
    db.add(obj)
    db.commit()
    return {"ok": True}


@router.get("/document-requirements", response_model=list[DocumentRequirementOut])
def list_document_requirements(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(DocumentRequirement).filter(DocumentRequirement.is_active.is_(True)).all()


@router.post("/document-requirements", response_model=DocumentRequirementOut, dependencies=[Depends(require_hr_admin)])
def create_document_requirement(payload: DocumentRequirementIn, db: Session = Depends(get_db)):
    obj = DocumentRequirement(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/document-requirements/{requirement_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_document_requirement(requirement_id: int, db: Session = Depends(get_db)):
    obj = db.query(DocumentRequirement).filter(DocumentRequirement.id == requirement_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document requirement not found")
    obj.is_active = False
    db.add(obj)
    db.commit()
    return {"ok": True}


@router.get("/driving-licence-requirements", response_model=list[DrivingLicenceRequirementOut])
def list_driving_licence_requirements(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(DrivingLicenceRequirement).filter(DrivingLicenceRequirement.is_active.is_(True)).all()


@router.post("/driving-licence-requirements", response_model=DrivingLicenceRequirementOut, dependencies=[Depends(require_hr_admin)])
def create_driving_licence_requirement(payload: DrivingLicenceRequirementIn, db: Session = Depends(get_db)):
    obj = DrivingLicenceRequirement(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/driving-licence-requirements/{requirement_id}", dependencies=[Depends(require_hr_admin)])
def deactivate_driving_licence_requirement(requirement_id: int, db: Session = Depends(get_db)):
    obj = db.query(DrivingLicenceRequirement).filter(DrivingLicenceRequirement.id == requirement_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driving Licence requirement not found")
    obj.is_active = False
    db.add(obj)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# RBAC administration (blueprint §18) - HR Admin only.
# ---------------------------------------------------------------------------

@router.get("/permissions", dependencies=[Depends(require_hr_admin)])
def list_permission_codes():
    return Permission.ALL


@router.get("/roles/{role_id}/permissions", dependencies=[Depends(require_hr_admin)])
def get_role_permissions(role_id: int, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    grants = db.query(RolePermission).filter(RolePermission.role_id == role_id).all()
    return {"role_id": role_id, "role_name": role.name, "permission_codes": [g.permission_code for g in grants]}


@router.put("/roles/{role_id}/permissions", dependencies=[Depends(require_hr_admin)])
def set_role_permissions(role_id: int, payload: RolePermissionsUpdate, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    invalid = set(payload.permission_codes) - set(Permission.ALL)
    if invalid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown permission code(s): {', '.join(invalid)}")
    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    for code in set(payload.permission_codes):
        db.add(RolePermission(role_id=role_id, permission_code=code))
    db.commit()
    return {"ok": True}


@router.get("/users/{user_id}/cost-center-scope", dependencies=[Depends(require_hr_admin)])
def get_user_cost_center_scope(user_id: int, db: Session = Depends(get_db)):
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    rows = db.query(UserCostCenterScope).filter(UserCostCenterScope.user_id == user_id).all()
    return {"user_id": user_id, "cost_center_ids": [r.cost_center_id for r in rows]}


@router.put("/users/{user_id}/cost-center-scope", dependencies=[Depends(require_hr_admin)])
def set_user_cost_center_scope(user_id: int, payload: CostCenterScopeUpdate, db: Session = Depends(get_db)):
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    cc_ids = set(payload.cost_center_ids)
    if cc_ids:
        found = db.query(CostCenter.id).filter(CostCenter.id.in_(cc_ids)).count()
        if found != len(cc_ids):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "One or more Cost Centers not found")
    db.query(UserCostCenterScope).filter(UserCostCenterScope.user_id == user_id).delete()
    for cc_id in cc_ids:
        db.add(UserCostCenterScope(user_id=user_id, cost_center_id=cc_id))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Approval routing rules (blueprint §15) - HR Admin only.
# ---------------------------------------------------------------------------

@router.get("/approval-rules", response_model=list[ApprovalRuleOut], dependencies=[Depends(require_hr_admin)])
def list_approval_rules(db: Session = Depends(get_db)):
    return db.query(ApprovalRule).all()


@router.post("/approval-rules", response_model=ApprovalRuleOut, dependencies=[Depends(require_hr_admin)])
def create_approval_rule(payload: ApprovalRuleIn, db: Session = Depends(get_db)):
    obj = ApprovalRule(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/approval-rules/{rule_id}", dependencies=[Depends(require_hr_admin)])
def delete_approval_rule(rule_id: int, db: Session = Depends(get_db)):
    obj = db.query(ApprovalRule).filter(ApprovalRule.id == rule_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval rule not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
