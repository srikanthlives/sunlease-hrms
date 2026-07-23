"""
Pydantic schemas (API contracts).
"""
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict
from .models import UserRole, ComponentType, CalculationType, EmployeeStatus, EntryType, AttendanceStatus


# ---------- Auth ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    username: str
    employee_id: int | None = None


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.EMPLOYEE
    employee_id: int | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool
    employee_id: int | None = None


# ---------- Salary Component / Template ----------
class SalaryComponentBase(BaseModel):
    code: str
    name: str
    component_type: ComponentType
    calculation_type: CalculationType
    value: float = 0
    formula: str | None = None
    is_variable: bool = False
    default_value: float = 0
    prorate_by_attendance: bool = False
    sequence: int = 0
    is_active: bool = True


class SalaryComponentCreate(SalaryComponentBase):
    pass


class SalaryComponentOut(SalaryComponentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    template_id: int


class SalaryTemplateCreate(BaseModel):
    template_no: str
    name: str
    description: str | None = None
    location: str | None = None
    components: list[SalaryComponentCreate] = []


class SalaryTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    location: str | None = None
    is_active: bool | None = None
    components: list[SalaryComponentCreate] | None = None  # full replace of components if provided


class SalaryTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    template_no: str
    name: str
    description: str | None
    location: str | None = None
    is_active: bool
    components: list[SalaryComponentOut] = []


class TemplateCloneRequest(BaseModel):
    template_no: str
    name: str
    location: str | None = None  # if omitted, keeps the source template's location


# ---------- Employee ----------
class EmployeeBase(BaseModel):
    employee_code: str
    first_name: str
    last_name: str = ""
    email: EmailStr | None = None
    phone: str | None = None
    department: str | None = None
    designation: str | None = None
    location: str | None = None
    date_of_joining: str | None = None
    date_of_leaving: str | None = None
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    template_id: int | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    ifsc: str | None = None
    pan: str | None = None
    uan: str | None = None
    pf_eligible: bool = True
    eps_eligible: bool = True
    esi_number: str | None = None
    esi_eligible: bool = True
    mediclaim_policy_no: str | None = None
    mediclaim_eligible: bool = True


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    employee_code: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    department: str | None = None
    designation: str | None = None
    location: str | None = None
    date_of_joining: str | None = None
    date_of_leaving: str | None = None
    status: EmployeeStatus | None = None
    template_id: int | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    ifsc: str | None = None
    pan: str | None = None
    uan: str | None = None
    pf_eligible: bool | None = None
    eps_eligible: bool | None = None
    esi_number: str | None = None
    esi_eligible: bool | None = None
    mediclaim_policy_no: str | None = None
    mediclaim_eligible: bool | None = None


class EmployeeOut(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    template: SalaryTemplateOut | None = None


# ---------- Employee <-> Template dated assignments ----------
class TemplateAssignmentIn(BaseModel):
    template_id: int
    effective_month: int  # 1-12
    effective_year: int


class TemplateAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    template_id: int
    effective_month: int
    effective_year: int
    created_at: datetime
    template: SalaryTemplateOut | None = None


# ---------- Attendance ----------
class AttendanceIn(BaseModel):
    employee_id: int
    month: int
    year: int
    total_days: float
    present_days: float
    paid_leave_days: float = 0
    lop_days: float = 0
    remarks: str | None = None


class AttendanceOut(AttendanceIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Day-by-day attendance ----------
class DailyAttendanceIn(BaseModel):
    employee_id: int
    date: str  # YYYY-MM-DD
    status: AttendanceStatus
    remarks: str | None = None


class DailyAttendanceOut(DailyAttendanceIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    uploaded_by: str | None = None


class AttendanceGridRow(BaseModel):
    employee_id: int
    employee_code: str
    name: str
    statuses: dict[str, str] = {}  # date (YYYY-MM-DD) -> status code
    total_days: float       # calendar days in the month
    present_days: float     # legacy alias for `total` (all paid days) - used by payroll
    lop_days: float
    paid_leave_days: float
    marked_days: int
    # Summary columns requested for the grid footer:
    total: float             # TOTAL = P + 2P*2 + WO + EL (+0.5*HD)
    present: float           # PRESENT = P + 2P*2 (+0.5*HD)
    week_offs: float
    rest_days: float
    absent: float
    el: float
    suspended: float
    lop: float               # LOP = max(0, AB - EL)


class AttendanceGridOut(BaseModel):
    month: int
    year: int
    days: list[int]  # 1..N calendar days in the month
    rows: list[AttendanceGridRow]


class ELBalanceOut(BaseModel):
    employee_id: int
    employee_code: str
    name: str
    worked_days: float
    accrued_el: int
    el_taken: float
    el_balance: float
    cap_reached: bool


# ---------- Monthly Variable Input ----------
class VariableInputIn(BaseModel):
    employee_id: int
    component_code: str
    month: int
    year: int
    value: float
    remarks: str | None = None


class VariableInputOut(VariableInputIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    uploaded_by: str | None = None
    uploaded_at: datetime


class BulkUploadResult(BaseModel):
    inserted: int
    updated: int
    errors: list[str] = []


# ---------- Adhoc Entries ----------
class AdhocEntryIn(BaseModel):
    employee_id: int
    month: int
    year: int
    label: str
    amount: float
    entry_type: EntryType
    remarks: str | None = None


class AdhocEntryOut(AdhocEntryIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_by: str | None = None
    created_at: datetime


# ---------- Salary Payments (part-payments made towards a month's salary) ----------
class SalaryPaymentIn(BaseModel):
    employee_id: int
    month: int
    year: int
    amount: float
    transaction_id: str | None = None
    payment_date: str | None = None
    remarks: str | None = None


class SalaryPaymentOut(SalaryPaymentIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    uploaded_by: str | None = None
    created_at: datetime


# ---------- Payroll / Payslip ----------
class RunPayrollRequest(BaseModel):
    month: int
    year: int
    employee_ids: list[int] | None = None  # None = all active employees


class PayslipLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    component_code: str
    component_name: str
    component_type: ComponentType
    amount: float
    source: str


class PayslipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    month: int
    year: int
    gross_earnings: float
    gross_deductions: float
    net_pay: float
    employer_cost_total: float | None = None
    ctc_total: float | None = None
    template_no: str | None = None
    present_days: float
    total_days: float
    generated_at: datetime
    lines: list[PayslipLineOut] = []
    payments: list[SalaryPaymentOut] = []
    total_paid: float = 0
    balance: float = 0


class RunPayrollResult(BaseModel):
    payroll_run_id: int
    generated: int
    failed: list[str] = []
    removed_stale: list[str] = []
    payslips: list[PayslipOut] = []


# ---------- Template component bulk upload ----------
class TemplateComponentsUploadResult(BaseModel):
    success: bool
    applied: int = 0          # components applied (0 if validation failed and nothing was applied)
    errors: list[str] = []    # row-level validation errors; if non-empty, nothing was applied


# ---------- Bank bulk payment file generation ----------
class BankPaymentGenerateRequest(BaseModel):
    month: int
    year: int
    debit_account_number: str
    transaction_date: str  # DD/MM/YYYY, as required by the bank file format
    coach_captain_designation: str = "Coach Captain"  # designation (case-insensitive) routed to the CC file
    remarks: str | None = None  # defaults to "Salary for <Mon> - <Year>" if not provided
    generation_mode: str = "full_salary"  # "full_salary" or "pending_payments" - see docstring below
