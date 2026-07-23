"""
Date-based employee payroll eligibility.

An employee is eligible for a given payroll period (month, year) if:
  - they had already joined by that period (date_of_joining's year/month <= period), and
  - they had not yet left before that period (date_of_leaving's year/month >= period,
    or no date_of_leaving is set at all).

This is driven entirely by dates, NOT by the `status` field. That's intentional:
  - If an employee's last working day is in April, they should still appear in April's
    payroll (even if their status hasn't been changed to "resigned" yet) and should be
    automatically excluded from May's payroll onward.
  - Conversely, forgetting to flip status to "resigned" must never cause someone to be
    overpaid in a later month - the date_of_leaving is what actually gates eligibility.
"""


def parse_year_month(date_str: str | None) -> tuple[int, int] | None:
    """Parse a 'YYYY-MM-DD' (or 'YYYY-MM') string into (year, month). Returns None if unset/unparseable."""
    if not date_str:
        return None
    try:
        parts = date_str.split("-")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


def is_eligible_for_period(employee, month: int, year: int) -> bool:
    period = (year, month)

    doj = parse_year_month(getattr(employee, "date_of_joining", None))
    if doj and doj > period:
        return False  # hasn't joined yet as of this period

    dol = parse_year_month(getattr(employee, "date_of_leaving", None))
    if dol and dol < period:
        return False  # already left before this period

    return True


def is_eligible_on_date(employee, date_str: str) -> bool:
    """Return True when a date falls within the employee's active window."""
    if not date_str:
        return False

    try:
        date_parts = date_str.split("-")
        if len(date_parts) != 3:
            return False
        date_value = tuple(int(part) for part in date_parts)
    except (ValueError, IndexError):
        return False

    doj = getattr(employee, "date_of_joining", None)
    if doj:
        try:
            doj_parts = doj.split("-")
            if len(doj_parts) >= 3:
                doj_value = tuple(int(part) for part in doj_parts[:3])
            else:
                doj_value = (int(doj_parts[0]), int(doj_parts[1]), 1)
            if date_value < doj_value:
                return False
        except (ValueError, IndexError):
            pass

    dol = getattr(employee, "date_of_leaving", None)
    if dol:
        try:
            dol_parts = dol.split("-")
            if len(dol_parts) >= 3:
                dol_value = tuple(int(part) for part in dol_parts[:3])
            else:
                dol_value = (int(dol_parts[0]), int(dol_parts[1]), 1)
            if date_value > dol_value:
                return False
        except (ValueError, IndexError):
            pass

    return True


def ineligibility_reason(employee, month: int, year: int) -> str | None:
    """Human-readable reason an employee is excluded, or None if they're eligible."""
    period = (year, month)
    doj = parse_year_month(getattr(employee, "date_of_joining", None))
    if doj and doj > period:
        return f"joins {employee.date_of_joining}, after this period"
    dol = parse_year_month(getattr(employee, "date_of_leaving", None))
    if dol and dol < period:
        return f"last working day was {employee.date_of_leaving}, before this period"
    return None
