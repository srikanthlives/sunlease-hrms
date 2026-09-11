from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator


class ShiftMasterIn(BaseModel):
    code: str
    name: str
    start_time: time
    end_time: time
    break_minutes: int = 0
    grace_minutes: int = 0
    half_day_hours: float | None = None
    full_day_hours: float | None = None
    is_night_shift: bool = False
    is_active: bool = True


class RosterGenerateIn(BaseModel):
    episode_id: int
    start_date: date
    end_date: date
    weekly_off_weekdays: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End Date cannot be before Start Date")
        for wd in self.weekly_off_weekdays:
            if wd < 0 or wd > 6:
                raise ValueError("weekly_off_weekdays entries must be 0-6 (Monday-Sunday)")
        return self


class WeeklyOffPatternIn(BaseModel):
    episode_id: int
    weekday: int = Field(ge=0, le=6)
    effective_from: date


class RosterEntryUpdate(BaseModel):
    shift_id: int | None = None
    second_shift_id: int | None = None
    is_rest_day: bool = False
    remarks: str | None = None


class AttendanceRecordIn(BaseModel):
    episode_id: int
    date: date
    check_in: datetime | None = None
    check_out: datetime | None = None
    shift_id: int | None = None
    status: str = "PRESENT"


class ExceptionResolveIn(BaseModel):
    resolution_remarks: str | None = None


class AttendanceRequestIn(BaseModel):
    episode_id: int
    date: date
    request_type: str  # CORRECTION/OVERTIME
    requested_check_in: datetime | None = None
    requested_check_out: datetime | None = None
    requested_overtime_minutes: int | None = Field(default=None, ge=0)
    reason: str | None = None

    @model_validator(mode="after")
    def _check_type(self):
        if self.request_type not in ("CORRECTION", "OVERTIME"):
            raise ValueError("request_type must be CORRECTION or OVERTIME")
        return self


class AttendanceRequestReview(BaseModel):
    remarks: str | None = None


class AttendanceBulkSaveItem(BaseModel):
    episode_id: int
    date: date
    status: str = "PRESENT"
    check_in: datetime | None = None
    check_out: datetime | None = None
    shift_id: int | None = None


class AttendanceBulkSaveIn(BaseModel):
    items: list[AttendanceBulkSaveItem] = Field(default_factory=list)
