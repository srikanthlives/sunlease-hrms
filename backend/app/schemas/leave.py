from datetime import date

from pydantic import BaseModel, Field, model_validator


class LeaveTypeIn(BaseModel):
    code: str
    name: str
    is_paid: bool = True
    accrual_frequency: str = "NONE"  # MONTHLY/YEARLY/NONE
    accrual_amount: float = 0
    max_balance: float | None = None
    carry_forward_limit: float | None = None
    requires_approval: bool = True
    is_active: bool = True


class LeaveEligibilityRuleIn(BaseModel):
    leave_type_id: int
    employee_category_id: int | None = None
    cost_center_id: int | None = None
    min_service_months: int = 0
    annual_entitlement: float = Field(ge=0)


class HolidayCalendarIn(BaseModel):
    name: str
    date: date
    cost_center_id: int | None = None
    is_optional: bool = False


class LeaveApplicationIn(BaseModel):
    episode_id: int
    leave_type_id: int
    start_date: date
    end_date: date
    is_half_day: bool = False
    half_day_session: str | None = None  # FIRST_HALF/SECOND_HALF
    reason: str | None = None

    @model_validator(mode="after")
    def _check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End Date cannot be before Start Date")
        if self.is_half_day and self.end_date != self.start_date:
            raise ValueError("A half-day leave must have the same Start and End Date")
        return self


class LeaveApplicationReview(BaseModel):
    remarks: str | None = None
