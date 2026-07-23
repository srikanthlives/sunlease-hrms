"""
Attendance calculation helpers.

Day-value convention (what each status contributes to a day's paid value):
    P  (Present)         -> 1.0
    2P (Double Present)  -> 2.0   (e.g. drivers who did double duty)
    HD (Half Day)        -> 0.5
    AB (Absent)          -> 0.0   (unpaid - contributes to loss-of-pay days)
    EL (Earned Leave)    -> 1.0   (paid, drawn from the EL balance)
    WO (Week Off)        -> 1.0   (paid, doesn't consume EL)
    R  (Rest Day)        -> 0.0   (unpaid compensatory rest, e.g. for drivers - not a worked
                                    day, not a paid day, not counted towards EL accrual)
    S  (Suspended)       -> 0.0   (separate count only; not counted towards total or present)

Monthly summary formulas (as used on the attendance grid and by payroll):
    TOTAL   = P + 2P*2 + WO + EL      (+ 0.5*HD, kept for backward compatibility)
    PRESENT = P + 2P*2                (+ 0.5*HD)
    WO      = count of WO days
    R       = count of R days
    AB      = count of AB days
    EL      = count of EL days
    S       = count of S days (separate total)
    LOP     = max(0, AB - EL)

Earned leave accrual rule: 1 EL for every 20 days actually WORKED (P/2P/HD only - EL, WO, and R
don't count as "worked"), capped at 15 EL per calendar year. EL balance = accrued - EL days
already taken this year. Marking a new day as EL is only allowed if the balance (as of that
month) has room for it - see check_el_available().
"""
import calendar
from sqlalchemy.orm import Session

from .. import models

# Value each status contributes towards total PAID days (used for payroll proration / TOTAL).
DAY_VALUE = {
    models.AttendanceStatus.PRESENT: 1.0,
    models.AttendanceStatus.DOUBLE_PRESENT: 2.0,
    models.AttendanceStatus.HALF_DAY: 0.5,
    models.AttendanceStatus.ABSENT: 0.0,
    models.AttendanceStatus.EARNED_LEAVE: 1.0,
    models.AttendanceStatus.WEEK_OFF: 1.0,
    models.AttendanceStatus.REST_DAY: 0.0,
    models.AttendanceStatus.SUSPENDED: 0.0,
}

# Value each status contributes towards physical PRESENCE only (excludes WO/EL/R).
PRESENT_VALUE = {
    models.AttendanceStatus.PRESENT: 1.0,
    models.AttendanceStatus.DOUBLE_PRESENT: 2.0,
    models.AttendanceStatus.HALF_DAY: 0.5,
    models.AttendanceStatus.ABSENT: 0.0,
    models.AttendanceStatus.EARNED_LEAVE: 0.0,
    models.AttendanceStatus.WEEK_OFF: 0.0,
    models.AttendanceStatus.REST_DAY: 0.0,
    models.AttendanceStatus.SUSPENDED: 0.0,
}

# Value each status contributes towards "days worked" for EL accrual purposes only.
WORKED_VALUE = {
    models.AttendanceStatus.PRESENT: 1.0,
    models.AttendanceStatus.DOUBLE_PRESENT: 2.0,
    models.AttendanceStatus.HALF_DAY: 0.5,
    models.AttendanceStatus.ABSENT: 0.0,
    models.AttendanceStatus.EARNED_LEAVE: 0.0,
    models.AttendanceStatus.WEEK_OFF: 0.0,
    models.AttendanceStatus.REST_DAY: 0.0,
    models.AttendanceStatus.SUSPENDED: 0.0,
}

EL_DAYS_PER_ACCRUAL = 20   # 1 EL earned per this many days worked
EL_ANNUAL_CAP = 15         # max EL accruable in a calendar year


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def compute_monthly_attendance_stats(db: Session, employee_id: int, month: int, year: int) -> dict | None:
    """
    Derive a month's attendance summary from DailyAttendance records. Returns None if there
    are no daily records at all for that employee/month (caller should fall back to the
    legacy monthly Attendance summary, or assume full attendance).
    """
    prefix = f"{year:04d}-{month:02d}-"
    records = (
        db.query(models.DailyAttendance)
        .filter(models.DailyAttendance.employee_id == employee_id)
        .filter(models.DailyAttendance.date.like(f"{prefix}%"))
        .all()
    )
    if not records:
        return None

    total = sum(DAY_VALUE.get(r.status, 0.0) for r in records)
    present_only = sum(PRESENT_VALUE.get(r.status, 0.0) for r in records)
    week_offs = sum(1.0 for r in records if r.status == models.AttendanceStatus.WEEK_OFF)
    rest_days = sum(1.0 for r in records if r.status == models.AttendanceStatus.REST_DAY)
    absent = sum(1.0 for r in records if r.status == models.AttendanceStatus.ABSENT)
    el = sum(1.0 for r in records if r.status == models.AttendanceStatus.EARNED_LEAVE)
    suspended = sum(1.0 for r in records if r.status == models.AttendanceStatus.SUSPENDED)
    lop = max(0.0, absent - el)

    return {
        # Legacy keys consumed by the payroll formula engine (TOTAL_DAYS/PRESENT_DAYS/etc.):
        "total_days": float(days_in_month(year, month)),
        "present_days": round(total, 2),       # payroll proration uses TOTAL (all paid days)
        "lop_days": round(lop, 2),
        "paid_leave_days": round(el, 2),
        "marked_days": len(records),
        # Detailed breakdown for the attendance grid summary:
        "total": round(total, 2),
        "present": round(present_only, 2),
        "week_offs": round(week_offs, 2),
        "rest_days": round(rest_days, 2),
        "absent": round(absent, 2),
        "el": round(el, 2),
        "suspended": round(suspended, 2),
        "lop": round(lop, 2),
    }


def compute_el_balance(db: Session, employee_id: int, year: int, upto_month: int = 12) -> dict:
    """
    Earned leave accrual for an employee for a calendar year, up to (and including) upto_month.
    1 EL accrues per 20 days worked, capped at 15/year. Balance = accrued - EL already taken.
    """
    start = f"{year:04d}-01-01"
    end_day = days_in_month(year, upto_month)
    end = f"{year:04d}-{upto_month:02d}-{end_day:02d}"

    records = (
        db.query(models.DailyAttendance)
        .filter(models.DailyAttendance.employee_id == employee_id)
        .filter(models.DailyAttendance.date >= start)
        .filter(models.DailyAttendance.date <= end)
        .all()
    )

    worked_days = sum(WORKED_VALUE.get(r.status, 0.0) for r in records)
    el_taken = sum(1.0 for r in records if r.status == models.AttendanceStatus.EARNED_LEAVE)
    accrued = min(int(worked_days // EL_DAYS_PER_ACCRUAL), EL_ANNUAL_CAP)
    balance = round(accrued - el_taken, 2)

    return {
        "worked_days": round(worked_days, 2),
        "accrued_el": accrued,
        "el_taken": round(el_taken, 2),
        "el_balance": balance,
        "cap_reached": accrued >= EL_ANNUAL_CAP,
    }


def check_el_available(db: Session, employee_id: int, date_str: str) -> str | None:
    """
    Returns an error message if marking this date as EL would exceed the employee's earned
    leave balance (as accrued up to that date's month), or None if it's fine to proceed.
    Marking a date that's ALREADY EL (no new consumption) is always allowed.
    """
    existing = db.query(models.DailyAttendance).filter_by(employee_id=employee_id, date=date_str).first()
    if existing and existing.status == models.AttendanceStatus.EARNED_LEAVE:
        return None

    year, month = int(date_str.split("-")[0]), int(date_str.split("-")[1])
    balance = compute_el_balance(db, employee_id, year, upto_month=month)
    if balance["el_balance"] <= 0:
        return (
            f"Insufficient earned leave balance: accrued {balance['accrued_el']}, "
            f"already taken {balance['el_taken']}, balance {balance['el_balance']}. "
            f"Cannot mark {date_str} as EL."
        )
    return None
