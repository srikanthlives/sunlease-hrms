"""
SQLAlchemy ORM models for the Salary/Payroll application.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    String, Integer, Float, Boolean, ForeignKey, DateTime, Enum, UniqueConstraint, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"                 # full access - manage templates, employees, users
    PAYROLL_PROCESSOR = "payroll_processor"  # HR/Payroll - attendance, uploads, run payroll
    EMPLOYEE = "employee"           # self-service - view own profile & payslips only


class ComponentType(str, enum.Enum):
    EARNING = "earning"
    DEDUCTION = "deduction"
    EMPLOYER_CONTRIBUTION = "employer_contribution"  # cost-to-company only; never shown on payslip,
    # never added to gross earnings/deductions or net pay. Feeds into CTC (Cost to Company) view only.
    # e.g. Employer PF contribution, Employer ESI, Gratuity accrual, Group insurance premium.
    REFERENCE = "reference"  # notional/helper value only - not paid, not a cost, never shown on
    # payslip or CTC totals. Exists purely so other components' formulas can refer to it,
    # e.g. GROSS_SALARY = BASIC + DA + HRA, then ESIC formula references GROSS_SALARY.


class CalculationType(str, enum.Enum):
    FIXED = "fixed"          # flat value
    FORMULA = "formula"      # expression referencing other component codes / attendance vars
    PERCENTAGE = "percentage"  # value is a % of a base amount; the base itself can be a full
    # formula expression (not just a single component code), e.g. "BASIC + DA"


class EmployeeStatus(str, enum.Enum):
    ACTIVE = "active"
    RESIGNED = "resigned"
    TERMINATED = "terminated"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "P"            # full day present -> 1.0 day
    DOUBLE_PRESENT = "2P"    # double duty (e.g. drivers) -> 2.0 days
    HALF_DAY = "HD"          # half day -> 0.5 day
    ABSENT = "AB"            # unpaid absence -> 0 days, contributes to loss-of-pay
    EARNED_LEAVE = "EL"      # paid earned leave -> 1.0 day, drawn from the EL balance
    WEEK_OFF = "WO"          # paid weekly off -> 1.0 day, doesn't consume EL
    REST_DAY = "R"           # unpaid rest day (e.g. drivers' compensatory rest) -> not counted
    # towards paid days, not counted towards EL accrual, tracked separately from week-off
    SUSPENDED = "S"           # suspended / unpaid day -> not counted towards total or present


class EntryType(str, enum.Enum):
    EARNING = "earning"
    DEDUCTION = "deduction"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.EMPLOYEE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="user", foreign_keys=[employee_id])
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SalaryTemplate(Base):
    __tablename__ = "salary_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(64), nullable=True)  # if set, only attachable to
    # employees at that same location; if null, it's a location-less/general template
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    components: Mapped[list["SalaryComponent"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="SalaryComponent.sequence"
    )
    employees: Mapped[list["Employee"]] = relationship(back_populates="template")


class SalaryComponent(Base):
    __tablename__ = "salary_components"
    __table_args__ = (UniqueConstraint("template_id", "code", name="uq_template_component_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("salary_templates.id"))
    code: Mapped[str] = mapped_column(String(32))          # e.g. BASIC, HRA, PERF_BONUS
    name: Mapped[str] = mapped_column(String(128))          # e.g. "Basic Pay"
    component_type: Mapped[ComponentType] = mapped_column(Enum(ComponentType))
    calculation_type: Mapped[CalculationType] = mapped_column(Enum(CalculationType))
    value: Mapped[float] = mapped_column(Float, default=0)  # fixed value OR % figure (0-100) for PERCENTAGE
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)  # expr for FORMULA, base code for PERCENTAGE
    is_variable: Mapped[bool] = mapped_column(Boolean, default=False)  # requires/accepts monthly manual override
    default_value: Mapped[float] = mapped_column(Float, default=0)     # default when variable & no override given
    prorate_by_attendance: Mapped[bool] = mapped_column(Boolean, default=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0)  # evaluation/display order hint
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    template: Mapped["SalaryTemplate"] = relationship(back_populates="components")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(64), nullable=True)  # office/branch/city
    date_of_joining: Mapped[str | None] = mapped_column(String(16), nullable=True)   # YYYY-MM-DD
    date_of_leaving: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[EmployeeStatus] = mapped_column(Enum(EmployeeStatus), default=EmployeeStatus.ACTIVE)
    # Legacy/default template - used only when no EmployeeTemplateAssignment applies for the
    # payroll month being computed (i.e. it covers everything before the earliest dated
    # assignment). Dated assignments below always take precedence when one applies.
    template_id: Mapped[int | None] = mapped_column(ForeignKey("salary_templates.id"), nullable=True)

    bank_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ifsc: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(16), nullable=True)
    uan: Mapped[str | None] = mapped_column(String(16), nullable=True)          # PF - Universal Account Number
    pf_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    eps_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    esi_number: Mapped[str | None] = mapped_column(String(20), nullable=True)   # ESI - IP (Insured Person) Number
    esi_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    mediclaim_policy_no: Mapped[str | None] = mapped_column(String(32), nullable=True)  # Mediclaim policy/member no.
    mediclaim_eligible: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    template: Mapped["SalaryTemplate"] = relationship(back_populates="employees")
    user: Mapped["User"] = relationship(back_populates="employee", uselist=False, foreign_keys="User.employee_id")


class EmployeeTemplateAssignment(Base):
    """
    A dated override of an employee's salary template, effective from a given month/year
    onward. Lets an employee move templates over time, e.g.:
      Jan 2026 -> Template A
      Mar 2026 -> Template B
      Mar 2027 -> Template C
    Payroll for Jan/Feb 2026 uses A, Mar 2026 - Feb 2027 uses B, Mar 2027 onward uses C.
    The most recent assignment whose (effective_year, effective_month) is <= the payroll
    period wins; if none apply yet, Employee.template_id is used as the fallback default.
    """
    __tablename__ = "employee_template_assignments"
    __table_args__ = (
        UniqueConstraint("employee_id", "effective_year", "effective_month", name="uq_emp_template_effective"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    template_id: Mapped[int] = mapped_column(ForeignKey("salary_templates.id"))
    effective_month: Mapped[int] = mapped_column(Integer)  # 1-12
    effective_year: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    employee: Mapped["Employee"] = relationship()
    template: Mapped["SalaryTemplate"] = relationship()


class MonthlyVariableInput(Base):
    """Monthly override for a variable salary component for a given employee (e.g. via Excel upload)."""
    __tablename__ = "monthly_variable_inputs"
    __table_args__ = (
        UniqueConstraint("employee_id", "component_code", "month", "year", name="uq_emp_component_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    component_code: Mapped[str] = mapped_column(String(32))
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    value: Mapped[float] = mapped_column(Float)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    employee: Mapped["Employee"] = relationship()


class Attendance(Base):
    """
    Legacy monthly attendance SUMMARY (total/present/paid-leave/LOP days entered directly for
    the whole month). Superseded by day-by-day DailyAttendance below, but kept as a fallback:
    if an employee/month has no daily records at all, payroll falls back to this row (or to
    "assume full attendance" if neither exists) so older data keeps working unchanged.
    """
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("employee_id", "month", "year", name="uq_emp_attendance_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    total_days: Mapped[float] = mapped_column(Float)
    present_days: Mapped[float] = mapped_column(Float)
    paid_leave_days: Mapped[float] = mapped_column(Float, default=0)
    lop_days: Mapped[float] = mapped_column(Float, default=0)  # loss of pay days
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    employee: Mapped["Employee"] = relationship()


class DailyAttendance(Base):
    """
    Day-by-day attendance record - the source of truth for the attendance management system.
    One row per employee per calendar date. A month's payroll attendance stats (present days,
    LOP days, paid leave days) are derived from these on the fly - see utils/attendance_calc.py.
    """
    __tablename__ = "daily_attendance"
    __table_args__ = (UniqueConstraint("employee_id", "date", name="uq_emp_attendance_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    status: Mapped[AttendanceStatus] = mapped_column(Enum(AttendanceStatus))
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    employee: Mapped["Employee"] = relationship()


class AdhocEntry(Base):
    """One-off manual earnings/deductions e.g. uniform deduction on resignation, ad-hoc reimbursement."""
    __tablename__ = "adhoc_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(128))
    amount: Mapped[float] = mapped_column(Float)
    entry_type: Mapped[EntryType] = mapped_column(Enum(EntryType))
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    employee: Mapped["Employee"] = relationship()


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("month", "year", name="uq_payroll_run_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    run_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    run_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="completed")

    payslips: Mapped[list["Payslip"]] = relationship(back_populates="payroll_run")


class Payslip(Base):
    __tablename__ = "payslips"
    __table_args__ = (UniqueConstraint("employee_id", "month", "year", name="uq_emp_payslip_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    payroll_run_id: Mapped[int | None] = mapped_column(ForeignKey("payroll_runs.id"), nullable=True)
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    gross_earnings: Mapped[float] = mapped_column(Float, default=0)
    gross_deductions: Mapped[float] = mapped_column(Float, default=0)
    net_pay: Mapped[float] = mapped_column(Float, default=0)
    employer_cost_total: Mapped[float] = mapped_column(Float, default=0)  # sum of EMPLOYER_CONTRIBUTION lines
    ctc_total: Mapped[float] = mapped_column(Float, default=0)            # gross_earnings + employer_cost_total
    template_no: Mapped[str | None] = mapped_column(String(32), nullable=True)  # which template was effective this month
    present_days: Mapped[float] = mapped_column(Float, default=0)
    total_days: Mapped[float] = mapped_column(Float, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    generated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    employee: Mapped["Employee"] = relationship()
    payroll_run: Mapped["PayrollRun"] = relationship(back_populates="payslips")
    lines: Mapped[list["PayslipLine"]] = relationship(back_populates="payslip", cascade="all, delete-orphan")


class PayslipLine(Base):
    __tablename__ = "payslip_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    payslip_id: Mapped[int] = mapped_column(ForeignKey("payslips.id"))
    component_code: Mapped[str] = mapped_column(String(32))
    component_name: Mapped[str] = mapped_column(String(128))
    component_type: Mapped[ComponentType] = mapped_column(Enum(ComponentType))
    amount: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32))  # template_default | variable_override | adhoc

    payslip: Mapped["Payslip"] = relationship(back_populates="lines")


class SalaryPayment(Base):
    """
    A payment actually made towards an employee's salary for a given month - salaries can be
    paid in multiple part-payments (e.g. an advance, then the balance later), each recorded
    with its own transaction ID. The payslip shows all of these plus the running balance
    (net_pay - sum of payments) for that month.
    """
    __tablename__ = "salary_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    amount: Mapped[float] = mapped_column(Float)
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_date: Mapped[str | None] = mapped_column(String(16), nullable=True)  # YYYY-MM-DD
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    employee: Mapped["Employee"] = relationship()
