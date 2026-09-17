from datetime import date

from pydantic import BaseModel, field_validator, model_validator

from app.core.validators import validate_aadhaar, validate_email_format, validate_mobile, validate_pan


class ChangeRequestReviewIn(BaseModel):
    remarks: str | None = None


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

    # Identity Documents - Name/DOB as printed on the card, alongside the
    # Number, for both Aadhaar and PAN (mirrors Employee's own fields;
    # copied over verbatim on conversion).
    aadhaar: str | None = None
    aadhaar_name: str | None = None
    aadhaar_dob: date | None = None
    pan: str | None = None
    pan_name: str | None = None
    pan_dob: date | None = None

    # Driving Licence - only shown/relevant when
    # licence_service.resolve_driving_licence_requirement_for_candidate
    # matches this candidate's applied Category/Designation.
    dl_licence_number: str | None = None
    dl_badge_number: str | None = None
    dl_vehicle_class: str | None = None
    dl_issuing_authority: str | None = None
    dl_issue_date: date | None = None
    dl_expiry_date: date | None = None

    applied_designation_id: int
    applied_employee_category_id: int
    applied_cost_center_id: int
    applied_project_id: int
    applied_date: date | None = None
    source: str | None = None
    remarks: str | None = None

    @field_validator("aadhaar")
    @classmethod
    def _check_aadhaar(cls, v):
        return validate_aadhaar(v) if v else v

    @field_validator("pan")
    @classmethod
    def _check_pan(cls, v):
        return validate_pan(v) if v else v

    @field_validator("mobile_number", "alternate_mobile_number")
    @classmethod
    def _check_mobile(cls, v):
        return validate_mobile(v) if v else v

    @field_validator("personal_email")
    @classmethod
    def _check_email(cls, v):
        return validate_email_format(v) if v else v

    @field_validator("total_experience_years")
    @classmethod
    def _check_experience(cls, v):
        if v is not None and not (0 <= v <= 60):
            raise ValueError("Total Experience must be between 0 and 60 years")
        return v

    @field_validator("date_of_birth", "aadhaar_dob", "pan_dob")
    @classmethod
    def _check_dob_not_future(cls, v):
        if v and v > date.today():
            raise ValueError("Date of Birth cannot be in the future")
        return v


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
