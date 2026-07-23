"""
Excel parsing helpers.

Expected file formats:

1. Employee upload, columns (case-insensitive), required marked with *:
     employee_code* | first_name* | last_name | email | phone | department | designation |
     location | date_of_joining | template_no | bank_name | bank_account | ifsc | pan | uan

2. Variable component upload (monthly overrides), columns (case-insensitive):
     employee_code | component_code | value | remarks (optional)

3. Attendance upload, columns:
     employee_code | total_days | present_days | paid_leave_days (optional) | lop_days (optional) | remarks (optional)

4. Salary template component bulk upload, columns:
     code | name | component_type | calculation_type | value | formula | is_variable |
     default_value | prorate_by_attendance | sequence

5. Salary payment upload (part-payments made towards a month's salary), columns:
     employee_code | amount | transaction_id (optional) | payment_date (optional) | remarks (optional)

6. Daily attendance - single day upload, columns:
     employee_code | status | remarks (optional)

7. Daily attendance - whole month upload, WIDE format: one row per employee, columns:
     employee_code | employee_name (optional, informational only - matching is by code) |
     1 | 2 | 3 | ... | <last day of the month>
   each day column holds that day's status code (P/2P/HD/AB/EL/WO/R), blank if unmarked.
"""
import io
import calendar
import datetime as dt
import pandas as pd


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    value = str(value).strip().lower()
    if value in {"1", "true", "yes", "y"}:
        return True
    if value in {"0", "false", "no", "n"}:
        return False
    return default


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def read_excel_bytes(content: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(content))
    return _normalize_columns(df)


def _opt_str(row, df, col) -> str | None:
    """Return a stripped string for an optional column, or None if missing/blank."""
    if col not in df.columns:
        return None
    value = row.get(col)
    if pd.isna(value) or str(value).strip() == "":
        return None
    if isinstance(value, (pd.Timestamp, dt.date, dt.datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def parse_employee_upload(content: bytes) -> list[dict]:
    df = read_excel_bytes(content)
    required = {"employee_code", "first_name"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("employee_code")) or pd.isna(row.get("first_name")):
            continue
        rows.append({
            "employee_code": str(row["employee_code"]).strip(),
            "first_name": str(row["first_name"]).strip(),
            "last_name": _opt_str(row, df, "last_name") or "",
            "email": _opt_str(row, df, "email"),
            "phone": _opt_str(row, df, "phone"),
            "department": _opt_str(row, df, "department"),
            "designation": _opt_str(row, df, "designation"),
            "location": _opt_str(row, df, "location"),
            "date_of_joining": _opt_str(row, df, "date_of_joining"),
            "template_no": _opt_str(row, df, "template_no"),
            "bank_name": _opt_str(row, df, "bank_name"),
            "bank_account": _opt_str(row, df, "bank_account"),
            "ifsc": _opt_str(row, df, "ifsc"),
            "pan": _opt_str(row, df, "pan"),
            "uan": _opt_str(row, df, "uan"),
            "pf_eligible": _parse_bool(_opt_str(row, df, "pf_eligible"), True),
            "eps_eligible": _parse_bool(_opt_str(row, df, "eps_eligible"), True),
            "esi_number": _opt_str(row, df, "esi_number"),
            "esi_eligible": _parse_bool(_opt_str(row, df, "esi_eligible"), True),
            "mediclaim_policy_no": _opt_str(row, df, "mediclaim_policy_no"),
            "mediclaim_eligible": _parse_bool(_opt_str(row, df, "mediclaim_eligible"), True),
        })
    return rows


def parse_variable_upload(content: bytes) -> list[dict]:
    df = read_excel_bytes(content)
    required = {"employee_code", "component_code", "value"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("employee_code")) or pd.isna(row.get("component_code")):
            continue
        rows.append({
            "employee_code": str(row["employee_code"]).strip(),
            "component_code": str(row["component_code"]).strip().upper(),
            "value": float(row["value"]) if not pd.isna(row.get("value")) else 0.0,
            "remarks": None if pd.isna(row.get("remarks")) else str(row.get("remarks")),
        })
    return rows


def parse_attendance_upload(content: bytes) -> list[dict]:
    df = read_excel_bytes(content)
    required = {"employee_code", "total_days", "present_days"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("employee_code")):
            continue
        rows.append({
            "employee_code": str(row["employee_code"]).strip(),
            "total_days": float(row["total_days"]),
            "present_days": float(row["present_days"]),
            "paid_leave_days": float(row["paid_leave_days"]) if "paid_leave_days" in df.columns and not pd.isna(row.get("paid_leave_days")) else 0.0,
            "lop_days": float(row["lop_days"]) if "lop_days" in df.columns and not pd.isna(row.get("lop_days")) else 0.0,
            "remarks": None if "remarks" not in df.columns or pd.isna(row.get("remarks")) else str(row.get("remarks")),
        })
    return rows


def parse_template_components_upload(content: bytes) -> list[dict]:
    """
    Parse a salary-template component bulk-upload file. Returns raw string/None values per
    row (as strings) - semantic validation (valid enum values, numeric parsing, formula
    syntax) is done by the caller so it can report row numbers against the original file.
    """
    df = read_excel_bytes(content)
    required = {"code", "name", "component_type", "calculation_type"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    def cell(row, col):
        if col not in df.columns:
            return None
        value = row.get(col)
        if pd.isna(value):
            return None
        return str(value).strip()

    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("code")) and pd.isna(row.get("name")):
            continue  # skip fully blank rows
        rows.append({
            "code": cell(row, "code"),
            "name": cell(row, "name"),
            "component_type": cell(row, "component_type"),
            "calculation_type": cell(row, "calculation_type"),
            "value": cell(row, "value"),
            "formula": cell(row, "formula"),
            "is_variable": cell(row, "is_variable"),
            "default_value": cell(row, "default_value"),
            "prorate_by_attendance": cell(row, "prorate_by_attendance"),
            "sequence": cell(row, "sequence"),
        })
    return rows


def parse_daily_attendance_day_upload(content: bytes) -> list[dict]:
    """Single-day bulk upload. Columns: employee_code, status, remarks (optional). The date
    itself is supplied separately (as a query param), not per-row."""
    df = read_excel_bytes(content)
    required = {"employee_code", "status"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("employee_code")) or pd.isna(row.get("status")):
            continue
        rows.append({
            "employee_code": str(row["employee_code"]).strip(),
            "status": str(row["status"]).strip().upper(),
            "remarks": _opt_str(row, df, "remarks"),
        })
    return rows


def _as_day_number(col) -> int | None:
    """Parses a column header like 1, 1.0, or '1' into the day number 1. Returns None if it's not a day column."""
    s = str(col).strip()
    try:
        f = float(s)
    except (TypeError, ValueError):
        return None
    if not f.is_integer():
        return None
    return int(f)


def parse_daily_attendance_wide_upload(content: bytes, year: int, month: int) -> list[dict]:
    """
    Whole-month bulk upload, WIDE format: one row per employee. Columns: employee_code,
    employee_name (optional, informational only - matching is by code), then one column per
    day of the month (1, 2, 3, ... up to 28/30/31 depending on the month), each holding that
    day's status code. Blank/missing day cells are simply left unmarked.

    Returns the same shape as the old long-format parser (a flat list of
    {employee_code, date, status, remarks}) so the rest of the pipeline is unchanged.
    """
    df = read_excel_bytes(content)
    if "employee_code" not in df.columns:
        raise ValueError("Missing required column: employee_code")

    n_days = calendar.monthrange(year, month)[1]
    day_col_map = {c: _as_day_number(c) for c in df.columns}
    day_col_map = {c: d for c, d in day_col_map.items() if d is not None and 1 <= d <= n_days}
    if not day_col_map:
        raise ValueError(f"No day columns found - expected columns named 1 through {n_days} for {month:02d}/{year}")

    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("employee_code")):
            continue
        employee_code = str(row["employee_code"]).strip()
        for col, day_num in day_col_map.items():
            value = row.get(col)
            if pd.isna(value):
                continue
            status = str(value).strip().upper()
            if not status:
                continue
            rows.append({
                "employee_code": employee_code,
                "date": f"{year:04d}-{month:02d}-{day_num:02d}",
                "status": status,
                "remarks": None,
            })
    return rows


def parse_payments_upload(content: bytes) -> list[dict]:
    df = read_excel_bytes(content)
    required = {"employee_code", "amount"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("employee_code")) or pd.isna(row.get("amount")):
            continue
        rows.append({
            "employee_code": str(row["employee_code"]).strip(),
            "amount": float(row["amount"]),
            "transaction_id": _opt_str(row, df, "transaction_id"),
            "payment_date": _opt_str(row, df, "payment_date"),
            "remarks": _opt_str(row, df, "remarks"),
        })
    return rows
