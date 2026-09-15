"""Bulk employee upload via .xlsx (blueprint §7 - creation wizard, batch
entry point). Each row creates a Draft Employee + EmploymentEpisode (same
status a single "New Employee" click starts at) with as much of Personal
Information / Address / Employment Information / Organizational
Assignment / Statutory / Bank / Dependents (up to 3) / Nominees (up to 3)
filled in as the row provides - Documents/Driving Licence stay
per-employee, filled in later via the wizard, since they don't fit a flat
spreadsheet row well (file-upload fields).
"""
import io
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.validators import validate_aadhaar, validate_ifsc, validate_mobile, validate_pan
from app.models.enums import AddressType, AuditAction, EpisodeStatus, RoleName, TransactionType
from app.models.models import (
    BankAccount, Dependent, Employee, EmploymentEpisode, Address, Nominee, OrgAssignment, StatutoryInfo,
    CostCenter, Department, Project, EmployeeCategory, EmployeeType, Designation, WorkLocation, User,
)
from app.services import audit_service, employee_service, approval_service

# (field_key, column_header). Order here is the order columns appear in
# the downloadable template. "*" in the header marks a required field.
COLUMNS = [
    ("employee_number", "Employee Number*"),
    ("first_name", "First Name*"),
    ("middle_name", "Middle Name"),
    ("last_name", "Last Name*"),
    ("father_husband_name", "Father's/Husband's Name"),
    ("gender", "Gender (MALE/FEMALE/OTHER)"),
    ("date_of_birth", "Date of Birth (YYYY-MM-DD)"),
    ("marital_status", "Marital Status (SINGLE/MARRIED/OTHER)"),
    ("educational_qualification", "Educational Qualification"),
    ("mobile_number", "Mobile Number"),
    ("alternate_mobile_number", "Alternate Mobile Number"),
    ("personal_email", "Personal Email"),
    ("official_email", "Official Email"),
    ("aadhaar", "Aadhaar"),
    ("pan", "PAN"),
    ("emergency_contact_name", "Emergency Contact Name"),
    ("emergency_contact_relationship", "Emergency Contact Relationship"),
    ("emergency_contact_mobile", "Emergency Contact Mobile"),
    ("previous_designation", "Previous Designation"),
    ("previous_company_name", "Previous Company Name"),
    ("previous_company_details", "Previous Company Details"),
    ("previous_date_of_joining", "Previous Date of Joining (YYYY-MM-DD)"),
    ("total_experience_years", "Total Experience (years)"),
    ("present_line1", "Present Address Line 1"),
    ("present_line2", "Present Address Line 2"),
    ("present_city", "Present City"),
    ("present_state", "Present State"),
    ("present_pincode", "Present Pincode"),
    ("present_country", "Present Country"),
    ("same_as_present", "Permanent Same As Present (YES/NO)"),
    ("permanent_line1", "Permanent Address Line 1"),
    ("permanent_line2", "Permanent Address Line 2"),
    ("permanent_city", "Permanent City"),
    ("permanent_state", "Permanent State"),
    ("permanent_pincode", "Permanent Pincode"),
    ("permanent_country", "Permanent Country"),
    ("employment_type", "Employment Type (must match Organization Setup)"),
    ("employee_category", "Employee Category (must match Organization Setup)"),
    ("designation", "Designation (must match Organization Setup)"),
    ("work_location", "Work Location (must match Organization Setup)"),
    ("shift_group", "Shift Group"),
    ("date_of_joining", "Date of Joining (YYYY-MM-DD)"),
    ("confirmation_date", "Confirmation Date (YYYY-MM-DD)"),
    ("cost_center", "Cost Center (must match Organization Setup)"),
    ("department", "Department (must match Organization Setup)"),
    ("project", "Project (must match Organization Setup, optional)"),
    ("assignment_effective_from", "Assignment Effective From (YYYY-MM-DD)"),
    ("pf_eligible", "PF Eligible (YES/NO)"),
    ("pf_name_on_file", "PF Name On File"),
    ("uan", "UAN"),
    ("pf_effective_date", "PF Effective Date (YYYY-MM-DD)"),
    ("esi_eligible", "ESI Eligible (YES/NO)"),
    ("esi_name_on_file", "ESI Name On File"),
    ("esi_number", "ESI Number"),
    ("esi_mediclaim_number", "ESI Mediclaim Number"),
    ("esi_effective_date", "ESI Effective Date (YYYY-MM-DD)"),
    ("pt_eligible", "PT Eligible (YES/NO)"),
    ("gratuity_eligible", "Gratuity Eligible (YES/NO)"),
    ("statutory_effective_from", "Statutory Effective From (YYYY-MM-DD)"),
    ("bank_name", "Bank Name"),
    ("bank_branch", "Bank Branch"),
    ("bank_account_number", "Bank Account Number"),
    ("bank_ifsc", "Bank IFSC"),
    ("bank_account_holder_name", "Bank Account Holder Name"),
    ("bank_account_type", "Bank Account Type"),
    ("bank_payment_mode", "Bank Payment Mode"),
    ("bank_effective_from", "Bank Effective From (YYYY-MM-DD)"),
    ("dependent_1_name", "Dependent 1 Name"),
    ("dependent_1_relationship", "Dependent 1 Relationship"),
    ("dependent_1_date_of_birth", "Dependent 1 Date of Birth (YYYY-MM-DD)"),
    ("dependent_2_name", "Dependent 2 Name"),
    ("dependent_2_relationship", "Dependent 2 Relationship"),
    ("dependent_2_date_of_birth", "Dependent 2 Date of Birth (YYYY-MM-DD)"),
    ("dependent_3_name", "Dependent 3 Name"),
    ("dependent_3_relationship", "Dependent 3 Relationship"),
    ("dependent_3_date_of_birth", "Dependent 3 Date of Birth (YYYY-MM-DD)"),
    ("nominee_1_name", "Nominee 1 Name"),
    ("nominee_1_relationship", "Nominee 1 Relationship"),
    ("nominee_1_date_of_birth", "Nominee 1 Date of Birth (YYYY-MM-DD)"),
    ("nominee_1_address", "Nominee 1 Address"),
    ("nominee_1_mobile", "Nominee 1 Mobile"),
    ("nominee_1_percentage", "Nominee 1 Percentage"),
    ("nominee_1_nomination_type", "Nominee 1 Nomination Type (PF/GRATUITY/INSURANCE/OTHER)"),
    ("nominee_2_name", "Nominee 2 Name"),
    ("nominee_2_relationship", "Nominee 2 Relationship"),
    ("nominee_2_date_of_birth", "Nominee 2 Date of Birth (YYYY-MM-DD)"),
    ("nominee_2_address", "Nominee 2 Address"),
    ("nominee_2_mobile", "Nominee 2 Mobile"),
    ("nominee_2_percentage", "Nominee 2 Percentage"),
    ("nominee_2_nomination_type", "Nominee 2 Nomination Type (PF/GRATUITY/INSURANCE/OTHER)"),
    ("nominee_3_name", "Nominee 3 Name"),
    ("nominee_3_relationship", "Nominee 3 Relationship"),
    ("nominee_3_date_of_birth", "Nominee 3 Date of Birth (YYYY-MM-DD)"),
    ("nominee_3_address", "Nominee 3 Address"),
    ("nominee_3_mobile", "Nominee 3 Mobile"),
    ("nominee_3_percentage", "Nominee 3 Percentage"),
    ("nominee_3_nomination_type", "Nominee 3 Nomination Type (PF/GRATUITY/INSURANCE/OTHER)"),
]

SAMPLE_ROW = {
    "employee_number": "EMP00200", "first_name": "Ravi", "middle_name": "", "last_name": "Kumar",
    "father_husband_name": "Suresh Kumar", "gender": "MALE", "date_of_birth": "1992-05-14",
    "marital_status": "MARRIED", "educational_qualification": "B.Com",
    "mobile_number": "9876543210", "alternate_mobile_number": "", "personal_email": "ravi.k@example.com",
    "official_email": "ravi.kumar@company.com", "aadhaar": "234123412341", "pan": "ABCDE1234F",
    "emergency_contact_name": "Suresh Kumar", "emergency_contact_relationship": "Father",
    "emergency_contact_mobile": "9876500000",
    "previous_designation": "Driver", "previous_company_name": "ABC Transport",
    "previous_company_details": "Local bus operator", "previous_date_of_joining": "2018-06-01",
    "total_experience_years": 5.5,
    "present_line1": "12 MG Road", "present_line2": "", "present_city": "Puducherry",
    "present_state": "Puducherry", "present_pincode": "605001", "present_country": "India",
    "same_as_present": "YES", "permanent_line1": "", "permanent_line2": "", "permanent_city": "",
    "permanent_state": "", "permanent_pincode": "", "permanent_country": "",
    "employment_type": "Permanent", "employee_category": "Driver", "designation": "Bus Driver",
    "work_location": "Puducherry Depot", "shift_group": "General Shift",
    "date_of_joining": "2026-01-01", "confirmation_date": "",
    "cost_center": "Puducherry", "department": "Operations", "project": "",
    "assignment_effective_from": "2026-01-01",
    "pf_eligible": "YES", "pf_name_on_file": "Ravi Kumar", "uan": "", "pf_effective_date": "2026-01-01",
    "esi_eligible": "NO", "esi_name_on_file": "", "esi_number": "", "esi_mediclaim_number": "", "esi_effective_date": "",
    "pt_eligible": "YES", "gratuity_eligible": "YES", "statutory_effective_from": "2026-01-01",
    "bank_name": "State Bank of India", "bank_branch": "Puducherry Main", "bank_account_number": "12345678901",
    "bank_ifsc": "SBIN0001234", "bank_account_holder_name": "Ravi Kumar", "bank_account_type": "Savings",
    "bank_payment_mode": "NEFT", "bank_effective_from": "2026-01-01",
    "dependent_1_name": "Lakshmi Kumar", "dependent_1_relationship": "Spouse", "dependent_1_date_of_birth": "1994-03-10",
    "dependent_2_name": "", "dependent_2_relationship": "", "dependent_2_date_of_birth": "",
    "dependent_3_name": "", "dependent_3_relationship": "", "dependent_3_date_of_birth": "",
    "nominee_1_name": "Lakshmi Kumar", "nominee_1_relationship": "Spouse", "nominee_1_date_of_birth": "1994-03-10",
    "nominee_1_address": "", "nominee_1_mobile": "", "nominee_1_percentage": 100, "nominee_1_nomination_type": "PF",
    "nominee_2_name": "", "nominee_2_relationship": "", "nominee_2_date_of_birth": "",
    "nominee_2_address": "", "nominee_2_mobile": "", "nominee_2_percentage": "", "nominee_2_nomination_type": "",
    "nominee_3_name": "", "nominee_3_relationship": "", "nominee_3_date_of_birth": "",
    "nominee_3_address": "", "nominee_3_mobile": "", "nominee_3_percentage": "", "nominee_3_nomination_type": "",
}


def build_template_workbook(db: Session) -> Workbook:
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Employees"

    headers = [header for _, header in COLUMNS]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    sheet.append([SAMPLE_ROW.get(key, "") for key, _ in COLUMNS])
    for col_idx, _ in enumerate(COLUMNS, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=col_idx).column_letter].width = 26

    ref = wb.create_sheet("Reference Values")
    ref.append(["Use these exact names in the matching columns on the Employees sheet"])
    ref["A1"].font = Font(bold=True)

    def _dump(row_label, col_letter, names):
        ref[f"{col_letter}1"] = row_label
        ref[f"{col_letter}1"].font = Font(bold=True)
        for i, name in enumerate(names, start=2):
            ref[f"{col_letter}{i}"] = name
        ref.column_dimensions[col_letter].width = 26

    ref.delete_rows(1)
    _dump("Cost Centers", "A", [c.name for c in db.query(CostCenter).filter(CostCenter.is_active.is_(True)).all()])
    _dump("Departments", "B", [d.name for d in db.query(Department).filter(Department.is_active.is_(True)).all()])
    _dump("Projects", "C", [p.name for p in db.query(Project).filter(Project.is_active.is_(True)).all()])
    _dump("Employee Categories", "D", [c.name for c in db.query(EmployeeCategory).filter(EmployeeCategory.is_active.is_(True)).all()])
    _dump("Employment Types", "E", [t.name for t in db.query(EmployeeType).filter(EmployeeType.is_active.is_(True)).all()])
    _dump("Designations", "F", [d.name for d in db.query(Designation).filter(Designation.is_active.is_(True)).all()])
    _dump("Work Locations", "G", [w.name for w in db.query(WorkLocation).filter(WorkLocation.is_active.is_(True)).all()])

    return wb


def _cell_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _cell_str_upper(value) -> str | None:
    """Same as _cell_str, but uppercased - used for text fields that get
    stored directly on a model (names, addresses, remarks, etc.), matching
    the same "everything in capital letters" convention the manual entry
    forms already apply (frontend/src/components/ui.jsx::Input). NOT used
    for values passed to _lookup() (master data names are matched
    case-sensitively against Organization Setup, which isn't necessarily
    all-uppercase) or for email addresses (case can be meaningful)."""
    text = _cell_str(value)
    return text.upper() if text else None


def _cell_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _cell_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cell_bool(value) -> bool:
    return (_cell_str(value) or "").upper() in ("YES", "Y", "TRUE", "1")


def _lookup(db: Session, model, name: str | None):
    if not name:
        return None
    return db.query(model).filter(model.name == name, model.is_active.is_(True)).first()


def _apply_or_request(db: Session, episode: EmploymentEpisode, transaction_type: str, changes: dict, actor: User) -> bool | None:
    """Mirrors routers/employees.py::_save_or_request exactly (HR_ADMIN or
    a non-ACTIVE episode applies directly, otherwise a ChangeRequest is
    queued) so a bulk-uploaded row updating an ACTIVE employee behaves
    identically to a human editing that employee by hand. Returns True if
    applied directly, False if queued, None if `changes` was empty (nothing
    to do)."""
    if not changes:
        return None
    if actor.role.name in (RoleName.HR_ADMIN, RoleName.SUPER_ADMIN) or episode.status != EpisodeStatus.ACTIVE:
        approval_service.apply_changes(db, episode, transaction_type, changes)
        audit_service.record(db, transaction_type, episode.id, AuditAction.UPDATE, actor, new_value="bulk upload")
        return True
    approval_service.create_change_request(db, episode, transaction_type, changes, actor)
    return False


# Personal/Identity fields (Employee model) a bulk-upload row can update on
# an existing match. Only non-empty cells are included per row so blank
# cells never blank out existing data.
_PERSONAL_STR_FIELDS = (
    "first_name", "middle_name", "last_name", "father_husband_name", "gender",
    "marital_status", "educational_qualification", "mobile_number", "alternate_mobile_number",
    "personal_email", "official_email", "emergency_contact_name",
    "emergency_contact_relationship", "emergency_contact_mobile",
    "previous_designation", "previous_company_name", "previous_company_details",
)
# Case is meaningful for these - never uppercased, unlike the rest of
# _PERSONAL_STR_FIELDS (see _cell_str_upper).
_NO_UPPERCASE_FIELDS = {"personal_email", "official_email"}
_PERSONAL_DATE_FIELDS = ("date_of_birth", "previous_date_of_joining")

# Employment fields (EmploymentEpisode model) - excludes employee_number,
# which is the row's match key, not a field to change.
_EMPLOYMENT_DATE_FIELDS = ("date_of_joining", "confirmation_date")


def _build_personal_changes(db: Session, data: dict) -> dict:
    changes = {}
    for field in _PERSONAL_STR_FIELDS:
        value = _cell_str(data.get(field)) if field in _NO_UPPERCASE_FIELDS else _cell_str_upper(data.get(field))
        if value is not None:
            changes[field] = value
    for field in _PERSONAL_DATE_FIELDS:
        value = _cell_date(data.get(field))
        if value is not None:
            changes[field] = value
    experience = _cell_float(data.get("total_experience_years"))
    if experience is not None:
        changes["total_experience_years"] = experience
    aadhaar = _cell_str(data.get("aadhaar"))
    if aadhaar is not None:
        changes["aadhaar"] = validate_aadhaar(aadhaar)
    pan = _cell_str(data.get("pan"))
    if pan is not None:
        changes["pan"] = validate_pan(pan)
    return changes


def _build_employment_changes(db: Session, data: dict) -> dict:
    changes = {}
    employment_type = _lookup(db, EmployeeType, _cell_str(data.get("employment_type")))
    if employment_type:
        changes["employment_type_id"] = employment_type.id
    employee_category = _lookup(db, EmployeeCategory, _cell_str(data.get("employee_category")))
    if employee_category:
        changes["employee_category_id"] = employee_category.id
    designation = _lookup(db, Designation, _cell_str(data.get("designation")))
    if designation:
        changes["designation_id"] = designation.id
    work_location = _lookup(db, WorkLocation, _cell_str(data.get("work_location")))
    if work_location:
        changes["work_location_id"] = work_location.id
    shift_group = _cell_str_upper(data.get("shift_group"))
    if shift_group is not None:
        changes["shift_group"] = shift_group
    for field in _EMPLOYMENT_DATE_FIELDS:
        value = _cell_date(data.get(field))
        if value is not None:
            changes[field] = value
    return changes


def _update_existing_row(db: Session, episode: EmploymentEpisode, data: dict, actor: User) -> dict:
    """Upserts an already-matched employee_number: applies changes through
    the exact same direct-apply / ChangeRequest branching a human edit
    would go through (_apply_or_request above), Address directly (never
    ChangeRequest-gated, same as today), and OrgAssignment directly
    (same convention OrgAssignment already follows everywhere else)."""
    employee = episode.employee

    personal_changes = _build_personal_changes(db, data)
    personal_applied = _apply_or_request(db, episode, TransactionType.IDENTITY_CHANGE, personal_changes, actor)

    employment_changes = _build_employment_changes(db, data)
    employment_applied = _apply_or_request(db, episode, TransactionType.EMPLOYMENT_CHANGE, employment_changes, actor)

    present_fields = {f: _cell_str_upper(data.get(f"present_{f}")) for f in ("line1", "line2", "city", "state", "pincode", "country")}
    if any(present_fields.values()):
        row = db.query(Address).filter(Address.employee_id == employee.id, Address.address_type == AddressType.PRESENT).first()
        if not row:
            row = Address(employee_id=employee.id, address_type=AddressType.PRESENT)
        for field, value in present_fields.items():
            if value is not None:
                setattr(row, field, value)
        db.add(row)

    same_as_present = (_cell_str(data.get("same_as_present")) or "").upper() in ("YES", "Y", "TRUE", "1")
    permanent_fields = present_fields if same_as_present else {f: _cell_str_upper(data.get(f"permanent_{f}")) for f in ("line1", "line2", "city", "state", "pincode", "country")}
    if any(permanent_fields.values()):
        row = db.query(Address).filter(Address.employee_id == employee.id, Address.address_type == AddressType.PERMANENT).first()
        if not row:
            row = Address(employee_id=employee.id, address_type=AddressType.PERMANENT)
        for field, value in permanent_fields.items():
            if value is not None:
                setattr(row, field, value)
        db.add(row)

    org_changed = False
    cost_center = _lookup(db, CostCenter, _cell_str(data.get("cost_center")))
    department = _lookup(db, Department, _cell_str(data.get("department")))
    if cost_center and department:
        current = db.query(OrgAssignment).filter(OrgAssignment.episode_id == episode.id, OrgAssignment.effective_to.is_(None)).first()
        if not current or current.cost_center_id != cost_center.id or current.department_id != department.id:
            project = _lookup(db, Project, _cell_str(data.get("project")))
            employee_service.add_org_assignment(db, episode.id, {
                "cost_center_id": cost_center.id, "department_id": department.id,
                "project_id": project.id if project else None,
                "effective_from": _cell_date(data.get("assignment_effective_from")) or date.today(),
            })
            audit_service.record(db, "ORG_ASSIGNMENT", episode.id, AuditAction.CREATE, actor, new_value="bulk upload")
            org_changed = True

    audit_service.record(db, "EMPLOYEE_DRAFT", episode.id, AuditAction.UPDATE, actor, new_value="bulk upload update")

    return {
        "updated": bool(personal_applied or employment_applied or any(present_fields.values()) or any(permanent_fields.values()) or org_changed),
        "submitted_for_approval": personal_applied is False or employment_applied is False,
    }


def import_workbook(db: Session, file_bytes: bytes, actor: User) -> dict:
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheet = wb["Employees"] if "Employees" in wb.sheetnames else wb.active

    header_row = [(_cell_str(c.value) or "") for c in sheet[1]]
    key_by_column_index = {}
    for idx, header in enumerate(header_row):
        for key, expected_header in COLUMNS:
            if header.strip().lower() == expected_header.strip().lower():
                key_by_column_index[idx] = key
                break

    created = 0
    updated = 0
    submitted_for_approval = 0
    errors = []

    for row_number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue  # skip blank rows

        data = {}
        for idx, value in enumerate(row):
            key = key_by_column_index.get(idx)
            if key:
                data[key] = value

        employee_number = _cell_str_upper(data.get("employee_number"))
        first_name = _cell_str_upper(data.get("first_name"))
        last_name = _cell_str_upper(data.get("last_name"))

        if not employee_number or not first_name or not last_name:
            errors.append({"row": row_number, "message": "Employee Number, First Name and Last Name are required"})
            continue

        savepoint = db.begin_nested()
        try:
            existing_episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == employee_number).first()
            if existing_episode:
                outcome = _update_existing_row(db, existing_episode, data, actor)
                savepoint.commit()
                if outcome["updated"]:
                    updated += 1
                if outcome["submitted_for_approval"]:
                    submitted_for_approval += 1
                continue

            aadhaar = _cell_str(data.get("aadhaar"))
            if aadhaar:
                aadhaar = validate_aadhaar(aadhaar)
            pan = _cell_str(data.get("pan"))
            if pan:
                pan = validate_pan(pan)

            employee = Employee(
                first_name=first_name, middle_name=_cell_str_upper(data.get("middle_name")), last_name=last_name,
                father_husband_name=_cell_str_upper(data.get("father_husband_name")),
                gender=_cell_str_upper(data.get("gender")), date_of_birth=_cell_date(data.get("date_of_birth")),
                marital_status=_cell_str_upper(data.get("marital_status")),
                educational_qualification=_cell_str_upper(data.get("educational_qualification")),
                mobile_number=_cell_str(data.get("mobile_number")),
                alternate_mobile_number=_cell_str(data.get("alternate_mobile_number")),
                personal_email=_cell_str(data.get("personal_email")), official_email=_cell_str(data.get("official_email")),
                aadhaar=aadhaar, pan=pan,
                emergency_contact_name=_cell_str_upper(data.get("emergency_contact_name")),
                emergency_contact_relationship=_cell_str_upper(data.get("emergency_contact_relationship")),
                emergency_contact_mobile=_cell_str(data.get("emergency_contact_mobile")),
                previous_designation=_cell_str_upper(data.get("previous_designation")),
                previous_company_name=_cell_str_upper(data.get("previous_company_name")),
                previous_company_details=_cell_str_upper(data.get("previous_company_details")),
                previous_date_of_joining=_cell_date(data.get("previous_date_of_joining")),
                total_experience_years=_cell_float(data.get("total_experience_years")),
            )
            db.add(employee)
            db.flush()

            present_fields = {f: _cell_str_upper(data.get(f"present_{f}")) for f in ("line1", "line2", "city", "state", "pincode", "country")}
            if any(present_fields.values()):
                db.add(Address(employee_id=employee.id, address_type=AddressType.PRESENT, **present_fields))

            same_as_present = (_cell_str(data.get("same_as_present")) or "").upper() in ("YES", "Y", "TRUE", "1")
            if same_as_present and any(present_fields.values()):
                db.add(Address(employee_id=employee.id, address_type=AddressType.PERMANENT, **present_fields))
            else:
                permanent_fields = {f: _cell_str_upper(data.get(f"permanent_{f}")) for f in ("line1", "line2", "city", "state", "pincode", "country")}
                if any(permanent_fields.values()):
                    db.add(Address(employee_id=employee.id, address_type=AddressType.PERMANENT, **permanent_fields))

            employment_type = _lookup(db, EmployeeType, _cell_str(data.get("employment_type")))
            employee_category = _lookup(db, EmployeeCategory, _cell_str(data.get("employee_category")))
            designation = _lookup(db, Designation, _cell_str(data.get("designation")))
            work_location = _lookup(db, WorkLocation, _cell_str(data.get("work_location")))

            episode = EmploymentEpisode(
                employee_id=employee.id, employee_number=employee_number, status=EpisodeStatus.DRAFT,
                employment_type_id=employment_type.id if employment_type else None,
                employee_category_id=employee_category.id if employee_category else None,
                designation_id=designation.id if designation else None,
                work_location_id=work_location.id if work_location else None,
                shift_group=_cell_str_upper(data.get("shift_group")),
                date_of_joining=_cell_date(data.get("date_of_joining")),
                confirmation_date=_cell_date(data.get("confirmation_date")),
            )
            db.add(episode)
            db.flush()

            cost_center = _lookup(db, CostCenter, _cell_str(data.get("cost_center")))
            department = _lookup(db, Department, _cell_str(data.get("department")))
            project = _lookup(db, Project, _cell_str(data.get("project")))
            if cost_center and department:
                employee_service.add_org_assignment(db, episode.id, {
                    "cost_center_id": cost_center.id, "department_id": department.id,
                    "project_id": project.id if project else None,
                    "effective_from": _cell_date(data.get("assignment_effective_from")) or date.today(),
                })

            if any(_cell_str(data.get(f)) for f in (
                "pf_name_on_file", "uan", "pf_effective_date", "esi_name_on_file", "esi_number",
                "esi_mediclaim_number", "esi_effective_date",
            )) or _cell_bool(data.get("pf_eligible")) or _cell_bool(data.get("esi_eligible")) \
                    or _cell_bool(data.get("pt_eligible")) or _cell_bool(data.get("gratuity_eligible")):
                db.add(StatutoryInfo(
                    episode_id=episode.id,
                    pf_eligible=_cell_bool(data.get("pf_eligible")),
                    pf_name_on_file=_cell_str_upper(data.get("pf_name_on_file")),
                    uan=_cell_str(data.get("uan")),
                    pf_effective_date=_cell_date(data.get("pf_effective_date")),
                    esi_eligible=_cell_bool(data.get("esi_eligible")),
                    esi_name_on_file=_cell_str_upper(data.get("esi_name_on_file")),
                    esi_number=_cell_str(data.get("esi_number")),
                    esi_mediclaim_number=_cell_str(data.get("esi_mediclaim_number")),
                    esi_effective_date=_cell_date(data.get("esi_effective_date")),
                    pt_eligible=_cell_bool(data.get("pt_eligible")),
                    gratuity_eligible=_cell_bool(data.get("gratuity_eligible")),
                    effective_from=_cell_date(data.get("statutory_effective_from")) or date.today(),
                ))

            bank_fields = {
                "bank_name": _cell_str_upper(data.get("bank_name")),
                "branch": _cell_str_upper(data.get("bank_branch")),
                "account_number": _cell_str(data.get("bank_account_number")),
                "ifsc": validate_ifsc(_cell_str(data.get("bank_ifsc"))) if _cell_str(data.get("bank_ifsc")) else None,
                "account_holder_name": _cell_str_upper(data.get("bank_account_holder_name")),
                "account_type": _cell_str_upper(data.get("bank_account_type")),
                "payment_mode": _cell_str_upper(data.get("bank_payment_mode")),
            }
            if any(bank_fields.values()):
                db.add(BankAccount(
                    episode_id=episode.id,
                    effective_from=_cell_date(data.get("bank_effective_from")) or date.today(),
                    **bank_fields,
                ))

            for n in (1, 2, 3):
                name = _cell_str_upper(data.get(f"dependent_{n}_name"))
                if not name:
                    continue
                db.add(Dependent(
                    episode_id=episode.id, name=name,
                    relationship_type=_cell_str_upper(data.get(f"dependent_{n}_relationship")),
                    date_of_birth=_cell_date(data.get(f"dependent_{n}_date_of_birth")),
                ))

            for n in (1, 2, 3):
                name = _cell_str_upper(data.get(f"nominee_{n}_name"))
                if not name:
                    continue
                mobile = _cell_str(data.get(f"nominee_{n}_mobile"))
                db.add(Nominee(
                    episode_id=episode.id, name=name,
                    relationship_type=_cell_str_upper(data.get(f"nominee_{n}_relationship")),
                    date_of_birth=_cell_date(data.get(f"nominee_{n}_date_of_birth")),
                    address=_cell_str_upper(data.get(f"nominee_{n}_address")),
                    mobile=validate_mobile(mobile) if mobile else None,
                    percentage=_cell_float(data.get(f"nominee_{n}_percentage")),
                    nomination_type=_cell_str(data.get(f"nominee_{n}_nomination_type")),
                ))

            audit_service.record(db, "EMPLOYEE_DRAFT", episode.id, AuditAction.CREATE, actor, new_value="bulk upload")
            savepoint.commit()
            created += 1
        except (ValueError, IntegrityError) as exc:
            savepoint.rollback()
            errors.append({"row": row_number, "message": str(exc.__cause__ or exc) if isinstance(exc, IntegrityError) else str(exc)})

    return {"created": created, "updated": updated, "submitted_for_approval": submitted_for_approval, "errors": errors}
