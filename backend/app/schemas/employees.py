from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.validators import (
    validate_aadhaar, validate_email_format, validate_ifsc, validate_mobile,
    validate_pan, validate_pincode,
)


class PersonalInfoStep(BaseModel):
    first_name: str
    middle_name: str | None = None
    last_name: str
    father_husband_name: str | None = None
    gender: str | None = None
    date_of_birth: date | None = None
    marital_status: str | None = None
    educational_qualification: str | None = None
    mobile_number: str | None = None
    alternate_mobile_number: str | None = None
    personal_email: str | None = None
    official_email: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_relationship: str | None = None
    emergency_contact_mobile: str | None = None
    aadhaar: str | None = None
    pan: str | None = None

    # Previous Experience (blueprint §12)
    previous_designation: str | None = None
    previous_company_name: str | None = None
    previous_company_details: str | None = None
    previous_date_of_joining: date | None = None
    total_experience_years: float | None = None

    @field_validator("aadhaar")
    @classmethod
    def _check_aadhaar(cls, v):
        return validate_aadhaar(v) if v else v

    @field_validator("pan")
    @classmethod
    def _check_pan(cls, v):
        return validate_pan(v) if v else v

    @field_validator("mobile_number", "alternate_mobile_number", "emergency_contact_mobile")
    @classmethod
    def _check_mobile(cls, v):
        return validate_mobile(v) if v else v

    @field_validator("personal_email", "official_email")
    @classmethod
    def _check_email(cls, v):
        return validate_email_format(v) if v else v

    @field_validator("date_of_birth")
    @classmethod
    def _check_dob_not_future(cls, v):
        if v and v > date.today():
            raise ValueError("Date of Birth cannot be in the future")
        return v


class DrivingLicenceStep(BaseModel):
    licence_number: str | None = None
    badge_number: str | None = None
    vehicle_class: str | None = None
    issuing_authority: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None

    @model_validator(mode="after")
    def _check_dates(self):
        if self.issue_date and self.expiry_date and self.expiry_date < self.issue_date:
            raise ValueError("Expiry Date cannot be before Issue Date")
        return self


class AddressStep(BaseModel):
    present_line1: str | None = None
    present_line2: str | None = None
    present_city: str | None = None
    present_state: str | None = None
    present_pincode: str | None = None
    present_country: str | None = None
    same_as_present: bool = False
    permanent_line1: str | None = None
    permanent_line2: str | None = None
    permanent_city: str | None = None
    permanent_state: str | None = None
    permanent_pincode: str | None = None
    permanent_country: str | None = None

    @field_validator("present_pincode", "permanent_pincode")
    @classmethod
    def _check_pincode(cls, v):
        return validate_pincode(v) if v else v


class EmploymentInfoStep(BaseModel):
    employee_number: str
    employment_type_id: int | None = None
    employee_category_id: int | None = None
    designation_id: int | None = None
    work_location_id: int | None = None
    shift_group: str | None = None
    date_of_joining: date | None = None
    confirmation_date: date | None = None

    @model_validator(mode="after")
    def _check_dates(self):
        if self.date_of_joining and self.confirmation_date and self.confirmation_date < self.date_of_joining:
            raise ValueError("Confirmation Date cannot be before Date of Joining")
        return self


class OrgAssignmentStep(BaseModel):
    cost_center_id: int
    project_id: int | None = None
    department_id: int
    reporting_manager_episode_id: int | None = None
    effective_from: date


class CostAllocationIn(BaseModel):
    cost_center_id: int
    project_id: int | None = None
    percentage: float = Field(gt=0, le=100)
    effective_from: date


class StatutoryInfoStep(BaseModel):
    pf_eligible: bool = False
    pf_name_on_file: str | None = None
    uan: str | None = None
    pf_effective_date: date | None = None

    esi_eligible: bool = False
    esi_name_on_file: str | None = None
    esi_number: str | None = None
    esi_mediclaim_number: str | None = None
    esi_effective_date: date | None = None

    pt_eligible: bool = False
    gratuity_eligible: bool = False


class BankAccountStep(BaseModel):
    bank_name: str | None = None
    branch: str | None = None
    account_number: str | None = None
    ifsc: str | None = None
    account_holder_name: str | None = None
    account_type: str | None = None
    payment_mode: str | None = None
    is_primary: bool = True
    effective_from: date

    @field_validator("ifsc")
    @classmethod
    def _check_ifsc(cls, v):
        return validate_ifsc(v) if v else v


class DependentIn(BaseModel):
    name: str
    relationship_type: str | None = None
    date_of_birth: date | None = None


class NomineeIn(BaseModel):
    name: str
    relationship_type: str | None = None
    date_of_birth: date | None = None
    address: str | None = None
    mobile: str | None = None
    percentage: float | None = Field(default=None, gt=0, le=100)
    nomination_type: str | None = None

    @field_validator("mobile")
    @classmethod
    def _check_mobile(cls, v):
        return validate_mobile(v) if v else v


class ChangeRequestReview(BaseModel):
    remarks: str | None = None


class SeparationIn(BaseModel):
    separation_type: str | None = None
    resignation_date: date | None = None
    notice_period_days: int | None = None
    last_working_date: date | None = None
    reason: str | None = None
    remarks: str | None = None

    @model_validator(mode="after")
    def _check_dates(self):
        if self.resignation_date and self.last_working_date and self.last_working_date < self.resignation_date:
            raise ValueError("Last Working Date cannot be before Resignation Date")
        return self


class SeparationChecklistUpdate(BaseModel):
    """Exit checklist, updated after the exit has been initiated
    (blueprint §16) - separate from SeparationIn since these are worked
    through over the notice period, not all captured at once."""
    last_working_date: date | None = None
    remarks: str | None = None
    exit_interview_done: bool = False
    asset_return_done: bool = False
    clearance_done: bool = False
    document_issuance_done: bool = False
    full_final_status: str = "PENDING"
