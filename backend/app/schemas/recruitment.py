from datetime import date

from pydantic import BaseModel, model_validator


class SelectionCriteriaIn(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True


class DesignationCriteriaIn(BaseModel):
    designation_id: int
    cost_center_id: int | None = None  # null = applies to the designation everywhere
    criteria_id: int
    is_mandatory: bool = True
    sequence: int = 0


class CandidateIn(BaseModel):
    first_name: str
    middle_name: str | None = None
    last_name: str
    father_husband_name: str | None = None
    gender: str | None = None
    date_of_birth: date | None = None
    mobile_number: str | None = None
    alternate_mobile_number: str | None = None
    personal_email: str | None = None
    educational_qualification: str | None = None
    current_designation: str | None = None
    current_company_name: str | None = None
    current_company_details: str | None = None
    current_date_of_joining: date | None = None
    total_experience_years: float | None = None
    aadhaar: str | None = None

    applied_designation_id: int
    applied_employee_category_id: int | None = None
    applied_cost_center_id: int
    applied_project_id: int | None = None
    applied_date: date | None = None
    source: str | None = None
    remarks: str | None = None


class CandidateStageResultIn(BaseModel):
    criteria_id: int
    result: str  # PENDING/PASS/FAIL
    tested_on: date | None = None
    remarks: str | None = None

    @model_validator(mode="after")
    def _check_result(self):
        if self.result not in ("PENDING", "PASS", "FAIL"):
            raise ValueError("result must be PENDING, PASS or FAIL")
        return self


class CandidateSalaryComponentIn(BaseModel):
    component_id: int
    amount: float | None = None
    percentage: float | None = None
    formula: str | None = None

    @model_validator(mode="after")
    def _check_one_of(self):
        if sum(v is not None for v in (self.amount, self.percentage, self.formula)) != 1:
            raise ValueError("Provide exactly one of amount, percentage, or formula")
        return self


class ConvertCandidateIn(BaseModel):
    employee_number: str
    date_of_joining: date
    employment_type_id: int | None = None
    employee_category_id: int | None = None
    work_location_id: int | None = None
    confirmation_date: date | None = None
