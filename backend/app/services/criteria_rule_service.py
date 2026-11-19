"""Auto-evaluated selection criteria: a rule over one of the candidate's own
date fields, instead of a human recording PASS/FAIL.

Every rule HR actually asks for turns out to be the same sentence - take a
date on the candidate, measure the time SINCE it or UNTIL it, and compare
that to a number:

    age under 55          date_of_birth    SINCE  <   55  YEARS
    licence 3 years old   dl_issue_date    SINCE  >=  3   YEARS
    licence not expired   dl_expiry_date   UNTIL  >=  0   DAYS
    licence good 6 more   dl_expiry_date   UNTIL  >=  6   MONTHS

So the rule is five dropdowns, not an expression language. There is nothing
to parse, nothing a typo can turn into a silently wrong rule, and the whole
catalog of what can be referenced is the dict below - unlike payroll's
formula engine, which needs arbitrary arithmetic and pays for it with
simpleeval.

Durations are CALENDAR-accurate, not days/365: someone born on 1 Jan 1971 is
exactly 55.0 on 1 Jan 2026 and 54.99 the day before, so "< 55 years" fails on
the birthday itself rather than a day or two either side.
"""
import datetime as dt

# field -> (label, where it lives on the candidate)
# Only dates, and only fields a candidate actually carries - anything not
# listed here simply cannot be referenced by a rule.
FIELDS = {
    "date_of_birth": "Date of Birth",
    "dl_issue_date": "Driving Licence Issue Date",
    "dl_expiry_date": "Driving Licence Expiry Date",
    "current_date_of_joining": "Current Employment Joining Date",
    "applied_date": "Application Date",
    "aadhaar_dob": "Date of Birth (as on Aadhaar)",
    "pan_dob": "Date of Birth (as on PAN)",
}

MEASURES = {
    "SINCE": "Time since the date (how old it is)",
    "UNTIL": "Time until the date (how long it stays valid)",
}

UNITS = ("YEARS", "MONTHS", "DAYS")

OPERATORS = {
    ">=": "at least",
    ">": "more than",
    "<=": "at most",
    "<": "less than",
    "==": "exactly",
}


def _add_months(d: dt.date, months: int) -> dt.date:
    """Calendar month arithmetic with end-of-month clamping (31 Jan + 1 month
    = 28/29 Feb), which is what an anniversary means to a person."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        next_month_start = dt.date(year + 1, 1, 1)
    else:
        next_month_start = dt.date(year, month + 1, 1)
    last_day = (next_month_start - dt.timedelta(days=1)).day
    return dt.date(year, month, min(d.day, last_day))


def _anniversaries_between(start: dt.date, end: dt.date, step_months: int) -> float:
    """Whole anniversaries from `start` to `end`, plus the fraction of the way
    to the next one. Negative when `end` precedes `start` (a licence that
    expired last month is -1.0 months "until" expiry, which is exactly what
    makes `>= 0` fail)."""
    if end < start:
        return -_anniversaries_between(end, start, step_months)
    whole = ((end.year - start.year) * 12 + (end.month - start.month)) // step_months
    while _add_months(start, (whole + 1) * step_months) <= end:
        whole += 1
    while whole > 0 and _add_months(start, whole * step_months) > end:
        whole -= 1
    anchor = _add_months(start, whole * step_months)
    following = _add_months(start, (whole + 1) * step_months)
    span = (following - anchor).days or 1
    return whole + (end - anchor).days / span


def duration_between(start: dt.date, end: dt.date, unit: str) -> float:
    if unit == "DAYS":
        return float((end - start).days)
    if unit == "MONTHS":
        return _anniversaries_between(start, end, 1)
    return _anniversaries_between(start, end, 12)


def is_auto(criteria) -> bool:
    return bool(getattr(criteria, "auto_field", None))


def describe(criteria) -> str | None:
    """The rule as one readable line, shown wherever the criteria appears so
    nobody has to reconstruct it from five dropdowns."""
    if not is_auto(criteria):
        return None
    field = FIELDS.get(criteria.auto_field, criteria.auto_field)
    measure = "Time since" if criteria.auto_measure == "SINCE" else "Time until"
    operator = OPERATORS.get(criteria.auto_operator, criteria.auto_operator)
    value = criteria.auto_value
    value = int(value) if value is not None and float(value).is_integer() else value
    unit = (criteria.auto_unit or "YEARS").lower()
    return f"{measure} {field} must be {operator} {value} {unit}"


def validate(criteria_data: dict) -> dict:
    """Checks a rule before it is stored. Raises a plain ValueError; the
    router turns it into a 400."""
    field = criteria_data.get("auto_field")
    if not field:
        # Not an auto criteria - clear the rest so a half-filled rule can
        # never sit on a manual criteria waiting to be noticed.
        for key in ("auto_field", "auto_measure", "auto_operator", "auto_value", "auto_unit"):
            criteria_data[key] = None
        return criteria_data
    if field not in FIELDS:
        raise ValueError(f"Unknown field '{field}' for an automatic rule")
    if criteria_data.get("auto_measure") not in MEASURES:
        raise ValueError("Choose whether to measure the time since or until the date")
    if criteria_data.get("auto_operator") not in OPERATORS:
        raise ValueError(f"Unknown comparison '{criteria_data.get('auto_operator')}'")
    if criteria_data.get("auto_unit") not in UNITS:
        raise ValueError("Choose a unit: years, months or days")
    if criteria_data.get("auto_value") is None:
        raise ValueError("Enter the value to compare against")
    # The candidate's own recorded data IS the evidence for an auto rule, so
    # there is nothing for anyone to upload and nothing to share in bulk.
    criteria_data["requires_attachment"] = False
    criteria_data["supports_bulk_upload"] = False
    return criteria_data


def evaluate(criteria, candidate, today: dt.date | None = None) -> tuple[str, str]:
    """(result, reason) for one auto criteria against one candidate.

    PENDING - and never PASS or FAIL - when the date the rule needs is
    blank: a missing date is not evidence the candidate met the requirement,
    nor evidence they failed it. PENDING already blocks conversion for a
    mandatory criterion, so the safe outcome comes free, and the reason names
    the field that needs filling in.
    """
    today = today or dt.date.today()
    value = getattr(candidate, criteria.auto_field, None)
    label = FIELDS.get(criteria.auto_field, criteria.auto_field)
    if value is None:
        return "PENDING", f"{label} is not recorded for this candidate"
    if isinstance(value, dt.datetime):
        value = value.date()

    unit = criteria.auto_unit or "YEARS"
    if criteria.auto_measure == "UNTIL":
        actual = duration_between(today, value, unit)
        phrasing = f"{label} is {_pretty(actual, unit)} away"
        if actual < 0:
            phrasing = f"{label} passed {_pretty(-actual, unit)} ago"
    else:
        actual = duration_between(value, today, unit)
        phrasing = f"{label} is {_pretty(actual, unit)} ago"

    threshold = float(criteria.auto_value)
    comparisons = {
        ">=": actual >= threshold, ">": actual > threshold,
        "<=": actual <= threshold, "<": actual < threshold,
        "==": abs(actual - threshold) < 1e-9,
    }
    passed = comparisons[criteria.auto_operator]
    needed = f"{OPERATORS[criteria.auto_operator]} {_trim(threshold)} {unit.lower()}"
    return ("PASS" if passed else "FAIL"), f"{phrasing} (needs {needed})"


def _trim(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _pretty(value: float, unit: str) -> str:
    return f"{_trim(round(value, 1))} {unit.lower()}"
