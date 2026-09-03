from pydantic import BaseModel


class CompanyIn(BaseModel):
    name: str


class CompanyOut(CompanyIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class CostCenterIn(BaseModel):
    company_id: int
    name: str
    code: str


class CostCenterOut(CostCenterIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class ProjectIn(BaseModel):
    cost_center_id: int
    name: str
    code: str


class ProjectOut(ProjectIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class DepartmentIn(BaseModel):
    cost_center_id: int
    name: str
    code: str


class DepartmentOut(DepartmentIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class EmployeeCategoryIn(BaseModel):
    name: str
    description: str | None = None


class EmployeeCategoryOut(EmployeeCategoryIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class WorkLocationIn(BaseModel):
    project_id: int
    name: str
    code: str


class WorkLocationOut(WorkLocationIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class DesignationIn(BaseModel):
    name: str
    description: str | None = None


class DesignationOut(DesignationIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class EmployeeTypeIn(BaseModel):
    name: str
    description: str | None = None


class EmployeeTypeOut(EmployeeTypeIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class DocumentTypeIn(BaseModel):
    name: str
    description: str | None = None


class DocumentTypeOut(DocumentTypeIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class DocumentRequirementIn(BaseModel):
    document_type_id: int
    employee_type_id: int | None = None
    employee_category_id: int | None = None
    designation_id: int | None = None
    is_mandatory: bool = True


class DocumentRequirementOut(DocumentRequirementIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class DrivingLicenceRequirementIn(BaseModel):
    employee_type_id: int | None = None
    employee_category_id: int | None = None
    designation_id: int | None = None
    is_required: bool = True


class DrivingLicenceRequirementOut(DrivingLicenceRequirementIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class RolePermissionsUpdate(BaseModel):
    permission_codes: list[str]  # full-replace


class CostCenterScopeUpdate(BaseModel):
    cost_center_ids: list[int]  # full-replace


class ApprovalRuleIn(BaseModel):
    cost_center_id: int | None = None
    employee_category_id: int | None = None
    transaction_type: str
    approver_role: str
    approver_user_id: int | None = None


class ApprovalRuleOut(ApprovalRuleIn):
    id: int

    class Config:
        from_attributes = True
