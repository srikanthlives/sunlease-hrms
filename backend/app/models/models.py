import datetime as dt

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text,
    Time, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


def now():
    return dt.datetime.utcnow()


# ---------------------------------------------------------------------------
# Auth / Identity
# ---------------------------------------------------------------------------

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    created_at = Column(DateTime, default=now)

    users = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    # Set when this login belongs to a specific employee (e.g. future
    # self-service login, blueprint §19) - optional in Phase 1.
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    role = relationship("Role", back_populates="users")
    employee = relationship("Employee", foreign_keys=[employee_id])


class RolePermission(Base):
    """Grants a permission code (models.enums.Permission) to a Role.
    HR_ADMIN is never granted rows here - it bypasses checks entirely
    (see core/deps.py::require_permission)."""

    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    permission_code = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=now)

    role = relationship("Role")


class UserCostCenterScope(Base):
    """Which Cost Centers a user may see/act on (blueprint §18). HR_ADMIN
    bypasses this entirely (sees everything); every other role with zero
    rows here sees nothing - mirrors sunlease-expms's
    project_accounts_users pattern for scoping Accounts users."""

    __tablename__ = "user_cost_center_scopes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=False)
    created_at = Column(DateTime, default=now)

    user = relationship("User")
    cost_center = relationship("CostCenter")


# ---------------------------------------------------------------------------
# Organization model (blueprint §2)
# ---------------------------------------------------------------------------

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    # Nullable at the DB level only for existing rows created before this
    # column existed (migrate.py never backfills) - the schema/UI require
    # it for every new/edited Company. Used as the first segment of a
    # recruitment Candidate's Application Reference Number (see
    # recruitment_service.generate_reference_number).
    code = Column(String(50), unique=True, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    cost_centers = relationship("CostCenter", back_populates="company")


class CostCenter(Base):
    __tablename__ = "cost_centers"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    company = relationship("Company", back_populates="cost_centers")
    projects = relationship("Project", back_populates="cost_center")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=False)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    cost_center = relationship("CostCenter", back_populates="projects")


class Department(Base):
    """Global, reusable label - not tied to any single Cost Center. An
    employee's OrgAssignment picks a Department independently of Cost
    Center; it exists purely so data can be filtered/reported by
    department across cost centers."""

    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class EmployeeCategory(Base):
    """Admin-configurable, per blueprint §13 - not hard-coded."""

    __tablename__ = "employee_categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    designations = relationship("Designation", back_populates="employee_category")


class WorkLocation(Base):
    """Admin-configurable, linked to a Project (each Project's site(s))."""

    __tablename__ = "work_locations"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(150), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(100))
    pincode = Column(String(20))
    country = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    project = relationship("Project")


class Designation(Base):
    """Admin-configurable job title master (e.g. Bus Driver, Conductor,
    Site Supervisor) - not hard-coded, same pattern as EmployeeCategory."""

    __tablename__ = "designations"

    id = Column(Integer, primary_key=True)
    employee_category_id = Column(Integer, ForeignKey("employee_categories.id"), nullable=True)
    name = Column(String(150), unique=True, nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    employee_category = relationship("EmployeeCategory", back_populates="designations")


class EmployeeType(Base):
    """Admin-configurable Employment Type master (Permanent/Contract/
    Probation/Apprentice etc.) - replaces the earlier hard-coded list."""

    __tablename__ = "employee_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class DocumentType(Base):
    """Admin-configurable document master (Aadhaar Card, PAN Card,
    Educational Certificate, etc.) - blueprint §14."""

    __tablename__ = "document_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class DocumentRequirement(Base):
    """Rule: this DocumentType is required (mandatory or optional) for
    employees matching the given scope. Each of employee_type_id/
    employee_category_id/designation_id is independently optional - null
    means "any" on that dimension, so a rule can be as broad (applies to
    everyone) or as narrow (a specific Type+Category+Designation
    combination) as needed. When multiple rules for the same DocumentType
    apply to one employee, the highest-priority rule's is_mandatory wins:
    Employee Type > Employee Category > Designation (see
    services/document_service.py::resolve_required_documents)."""

    __tablename__ = "document_requirements"

    id = Column(Integer, primary_key=True)
    document_type_id = Column(Integer, ForeignKey("document_types.id"), nullable=False)
    employee_type_id = Column(Integer, ForeignKey("employee_types.id"), nullable=True)
    employee_category_id = Column(Integer, ForeignKey("employee_categories.id"), nullable=True)
    designation_id = Column(Integer, ForeignKey("designations.id"), nullable=True)
    is_mandatory = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    document_type = relationship("DocumentType")
    employee_type = relationship("EmployeeType")
    employee_category = relationship("EmployeeCategory")
    designation = relationship("Designation")


class DrivingLicenceRequirement(Base):
    """Whether the Driving Licence wizard step is shown at all for an
    employee, scoped by Employee Type / Category / Designation - same
    optional-dimension, most-specific-wins matching as DocumentRequirement
    (Employee Type > Category > Designation), see
    services/licence_service.py::resolve_driving_licence_requirement. No
    matching rule = the step is skipped entirely."""

    __tablename__ = "driving_licence_requirements"

    id = Column(Integer, primary_key=True)
    employee_type_id = Column(Integer, ForeignKey("employee_types.id"), nullable=True)
    employee_category_id = Column(Integer, ForeignKey("employee_categories.id"), nullable=True)
    designation_id = Column(Integer, ForeignKey("designations.id"), nullable=True)
    is_required = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    employee_type = relationship("EmployeeType")
    employee_category = relationship("EmployeeCategory")
    designation = relationship("Designation")


# ---------------------------------------------------------------------------
# Employee (person) / Employment Episode (blueprint §3)
# ---------------------------------------------------------------------------

class Employee(Base):
    """The person. Fields here never change across a rejoin - see
    EmploymentEpisode for the per-stint data."""

    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    first_name = Column(String(100), nullable=False)
    middle_name = Column(String(100))
    last_name = Column(String(100), nullable=False)
    father_husband_name = Column(String(255))
    gender = Column(String(20))
    date_of_birth = Column(Date)
    marital_status = Column(String(20))
    photo_object_key = Column(String(500))
    mobile_number = Column(String(20))
    alternate_mobile_number = Column(String(20))
    personal_email = Column(String(255))
    official_email = Column(String(255))
    educational_qualification = Column(String(255))

    # Previous Experience (blueprint §12 - Previous Employment)
    previous_designation = Column(String(150))
    previous_company_name = Column(String(255))
    previous_company_details = Column(Text)
    previous_date_of_joining = Column(Date)
    total_experience_years = Column(Float)

    # Legacy free-text address columns (Phase 1) - superseded by the
    # structured `Address` table below (one PRESENT + one PERMANENT row
    # per employee, entered in its own wizard step). Kept only because
    # migrate.py never drops columns; no longer read or written.
    present_address = Column(Text)
    permanent_address = Column(Text)
    emergency_contact_name = Column(String(255))
    emergency_contact_relationship = Column(String(100))
    emergency_contact_mobile = Column(String(20))
    # Identity Documents subsection - Name/DOB as printed on the card,
    # alongside the Number, for both Aadhaar and PAN (previously just the
    # bare number). Name commonly differs slightly from the employee's own
    # name (middle name omitted, spelling variants), and DOB on the card
    # is what gets cross-checked against official records, so both are
    # captured rather than assumed to match Personal Information.
    aadhaar = Column(String(20))
    aadhaar_name = Column(String(255))
    aadhaar_dob = Column(Date)
    pan = Column(String(20))
    pan_name = Column(String(255))
    pan_dob = Column(Date)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    episodes = relationship("EmploymentEpisode", back_populates="employee", foreign_keys="EmploymentEpisode.employee_id")
    addresses = relationship("Address", back_populates="employee")


class Address(Base):
    """Structured address (blueprint §4.1 Present/Permanent Address) -
    exactly one PRESENT and one PERMANENT row per Employee (upserted, not
    effective-dated - unlike OrgAssignment/StatutoryInfo, addresses have
    no historical-tracking requirement in the blueprint)."""

    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    address_type = Column(String(20), nullable=False)  # PRESENT or PERMANENT

    line1 = Column(String(255))
    line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(100))
    pincode = Column(String(20))
    country = Column(String(100))

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    employee = relationship("Employee", back_populates="addresses")


class EmploymentEpisode(Base):
    """One row per period of employment (blueprint §3). Rejoining creates a
    new episode rather than a new Employee/duplicate person record."""

    __tablename__ = "employment_episodes"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    employee_number = Column(String(50), unique=True, nullable=False)

    # Legacy free-text columns (Phase 1) - superseded by the FK master
    # tables below (Designation/WorkLocation/EmployeeType, admin-managed
    # under Organization Setup). Kept only because migrate.py never drops
    # columns; the Python attribute is renamed so it doesn't collide with
    # the new relationship of the same conceptual name.
    employment_type_legacy = Column("employment_type", String(30))
    designation_legacy = Column("designation", String(150))
    work_location_legacy = Column("work_location", String(150))

    employee_category_id = Column(Integer, ForeignKey("employee_categories.id"), nullable=True)
    employment_type_id = Column(Integer, ForeignKey("employee_types.id"), nullable=True)
    designation_id = Column(Integer, ForeignKey("designations.id"), nullable=True)
    work_location_id = Column(Integer, ForeignKey("work_locations.id"), nullable=True)
    shift_group = Column(String(100))

    date_of_joining = Column(Date)
    confirmation_date = Column(Date)
    application_reference_number = Column(String(50))

    status = Column(String(30), default="DRAFT", nullable=False)

    separation_date = Column(Date)
    separation_reason = Column(String(255))

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    employee = relationship("Employee", back_populates="episodes", foreign_keys=[employee_id])
    employee_category = relationship("EmployeeCategory")
    employee_type = relationship("EmployeeType")
    designation = relationship("Designation")
    work_location = relationship("WorkLocation")
    assignments = relationship("OrgAssignment", back_populates="episode", foreign_keys="OrgAssignment.episode_id")
    allocations = relationship("CostAllocation", back_populates="episode")
    statutory_records = relationship("StatutoryInfo", back_populates="episode")
    driving_licence = relationship("DrivingLicenceDetail", back_populates="episode", uselist=False)
    separation = relationship("SeparationRecord", back_populates="episode", uselist=False)
    bank_accounts = relationship("BankAccount", back_populates="episode")
    dependents = relationship("Dependent", back_populates="episode")
    nominees = relationship("Nominee", back_populates="episode")
    documents = relationship("DocumentMeta", back_populates="episode")


# ---------------------------------------------------------------------------
# Effective-dated organizational assignment + cost allocation (blueprint §5, §6)
# ---------------------------------------------------------------------------

class OrgAssignment(Base):
    """Effective-dated org placement. Never overwritten - a new placement
    closes the prior row's effective_to. Enforces: one active Department per
    employee at a time (blueprint §21)."""

    __tablename__ = "org_assignments"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    reporting_manager_episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=True)

    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", back_populates="assignments", foreign_keys=[episode_id])
    cost_center = relationship("CostCenter")
    project = relationship("Project")
    department = relationship("Department")
    reporting_manager_episode = relationship("EmploymentEpisode", foreign_keys=[reporting_manager_episode_id])


class CostAllocation(Base):
    """Effective-dated financial allocation, independent of org assignment
    (blueprint §6). Active rows should total 100% (recommended, not hard-blocked)."""

    __tablename__ = "cost_allocations"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    percentage = Column(Float, nullable=False)

    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", back_populates="allocations")
    cost_center = relationship("CostCenter")
    project = relationship("Project")


# ---------------------------------------------------------------------------
# Statutory / Bank / Dependents / Nominees / Documents (blueprint §4.2, §10-14)
# ---------------------------------------------------------------------------

class StatutoryInfo(Base):
    """Effective-dated because PF/ESI/PT/Gratuity eligibility can start
    later in employment (blueprint §4.2). Grouped PF / ESI fields, each
    gated behind its own eligibility flag (stored as a separate field, not
    inferred) - a group's detail fields are only meaningful once its
    eligibility flag is set, enforced client-side by disabling the group."""

    __tablename__ = "statutory_info"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)

    pf_eligible = Column(Boolean, default=False)
    pf_name_on_file = Column(String(255))
    uan = Column(String(30))  # "UAN / Member ID"
    pf_effective_date = Column(Date)

    esi_eligible = Column(Boolean, default=False)
    esi_name_on_file = Column(String(255))
    esi_number = Column(String(30))  # "ESI Number / Member ID"
    esi_mediclaim_number = Column(String(50))
    esi_effective_date = Column(Date)

    pt_eligible = Column(Boolean, default=False)
    gratuity_eligible = Column(Boolean, default=False)

    # Legacy (Phase 1) columns - superseded by the pf_*/esi_* fields above
    # and the removal of Driving Licence from Statutory Information. Kept
    # only because migrate.py never drops columns; no longer read/written.
    pf_number = Column(String(30))
    driving_licence_number = Column(String(30))
    driving_licence_expiry = Column(Date)

    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", back_populates="statutory_records")


class DrivingLicenceDetail(Base):
    """Standalone Driving Licence form (blueprint §4.2), only shown in the
    wizard when a DrivingLicenceRequirement rule matches the employee -
    see services/licence_service.py. One row per episode (upserted, like
    Address - no historical-tracking requirement)."""

    __tablename__ = "driving_licence_details"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False, unique=True)

    licence_number = Column(String(50))
    badge_number = Column(String(50))  # PSV/commercial driver badge, issued alongside the licence
    vehicle_class = Column(String(100))
    issuing_authority = Column(String(255))
    issue_date = Column(Date)
    expiry_date = Column(Date)

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    episode = relationship("EmploymentEpisode", back_populates="driving_licence")


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)

    bank_name = Column(String(150))
    branch = Column(String(150))
    account_number = Column(String(50))
    ifsc = Column(String(20))
    account_holder_name = Column(String(255))
    account_type = Column(String(30))
    payment_mode = Column(String(30))
    is_primary = Column(Boolean, default=True)
    verification_status = Column(String(20), default="PENDING")

    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", back_populates="bank_accounts")


class Dependent(Base):
    __tablename__ = "dependents"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)

    name = Column(String(255), nullable=False)
    relationship_type = Column(String(50))
    date_of_birth = Column(Date)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", back_populates="dependents")


class Nominee(Base):
    __tablename__ = "nominees"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)

    name = Column(String(255), nullable=False)
    relationship_type = Column(String(50))
    date_of_birth = Column(Date)
    address = Column(Text)
    mobile = Column(String(20))
    percentage = Column(Float)
    nomination_type = Column(String(20))  # PF, GRATUITY, INSURANCE, OTHER

    effective_from = Column(Date)
    effective_to = Column(Date)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", back_populates="nominees")


class DocumentMeta(Base):
    """One row per (episode, DocumentType) - re-uploading replaces the
    file on disk and updates this same row rather than versioning
    (see services/document_service.py::save_upload). Stored locally under
    HRMS_UPLOAD_DIR/<company>/<employee_number>/<document type name>.<ext>
    (blueprint §14 - R2 wiring can swap the storage backend later without
    changing this schema)."""

    __tablename__ = "document_meta"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    document_type_id = Column(Integer, ForeignKey("document_types.id"), nullable=True)

    document_type = Column(String(100), nullable=False)  # denormalized DocumentType.name snapshot, for display without a join
    file_name = Column(String(500))
    object_key = Column(String(500))
    file_size = Column(Integer)
    mime_type = Column(String(100))
    version = Column(Integer, default=1)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    issue_date = Column(Date)
    expiry_date = Column(Date)
    verification_status = Column(String(20), default="PENDING")
    verified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", back_populates="documents")
    document_type_master = relationship("DocumentType")


# ---------------------------------------------------------------------------
# Separation / Change Requests / Audit (blueprint §15, §16, §20)
# ---------------------------------------------------------------------------

class SeparationRecord(Base):
    __tablename__ = "separation_records"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False, unique=True)

    separation_type = Column(String(30))
    resignation_date = Column(Date)
    notice_period_days = Column(Integer)
    last_working_date = Column(Date)
    reason = Column(String(255))
    remarks = Column(Text)
    exit_interview_done = Column(Boolean, default=False)
    asset_return_done = Column(Boolean, default=False)
    clearance_done = Column(Boolean, default=False)
    document_issuance_done = Column(Boolean, default=False)
    full_final_status = Column(String(20), default="PENDING")
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", back_populates="separation")


class ApprovalRule(Base):
    """Routes an approval to a role/user by Cost Center + Employee
    Category + Transaction Type (blueprint §15). cost_center_id and/or
    employee_category_id may be null to act as a fallback - matched
    most-specific-first in services/approval_service.py::find_approval_rule,
    the same fallback idea as sunlease-expms's Project.accounts_approver_id."""

    __tablename__ = "approval_rules"

    id = Column(Integer, primary_key=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    employee_category_id = Column(Integer, ForeignKey("employee_categories.id"), nullable=True)
    transaction_type = Column(String(30), nullable=False)
    approver_role = Column(String(50), nullable=False)
    approver_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now)

    cost_center = relationship("CostCenter")
    employee_category = relationship("EmployeeCategory")
    approver_user = relationship("User")


class ChangeRequest(Base):
    """Approval-workflow record for edits to an already-ACTIVE employee
    (blueprint §15 - "Approved data must not be overwritten directly").
    `changes_json`/`previous_values_json` hold a JSON dict of
    field -> value for the whole edit (multiple fields per request), same
    shape as sunlease-expms's EditRequest.changes/previous_values. The
    legacy entity/field_name/old_value/new_value columns below predate
    this and are unused by the current flow (kept only because migrate.py
    never drops columns)."""

    __tablename__ = "change_requests"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)

    # Legacy (Phase 1) columns - unused by the v2 flow, see docstring.
    entity = Column(String(100), nullable=True)
    field_name = Column(String(100), nullable=True)
    old_value = Column(Text)
    new_value = Column(Text)
    effective_date = Column(Date)

    transaction_type = Column(String(30))
    changes_json = Column(Text)
    previous_values_json = Column(Text)
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_remarks = Column(Text)
    status = Column(String(20), default="PENDING")
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode")
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])


class AuditLog(Base):
    """Append-only for normal users (blueprint §20)."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=now)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(100))
    role = Column(String(50))
    module = Column(String(50), default="EMPLOYEE_DATA_MANAGEMENT")
    action = Column(String(30), nullable=False)
    entity = Column(String(100), nullable=False)
    record_id = Column(String(50), nullable=False)
    old_value = Column(Text)
    new_value = Column(Text)
    ip_address = Column(String(50))
    user_agent = Column(String(255))


# ---------------------------------------------------------------------------
# Module 2: Attendance (blueprint §23)
# ---------------------------------------------------------------------------

class ShiftMaster(Base):
    """Admin-configurable shift master (General/Morning/Night etc.)."""

    __tablename__ = "shift_masters"

    id = Column(Integer, primary_key=True)
    code = Column(String(30), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    break_minutes = Column(Integer, default=0)
    grace_minutes = Column(Integer, default=0)
    half_day_hours = Column(Float, nullable=True)
    full_day_hours = Column(Float, nullable=True)
    is_night_shift = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class WeeklyOffPattern(Base):
    """Effective-dated recurring weekly-off rule (e.g. "Sunday off") - a
    generator, not the source of truth; generate_roster() materializes it
    into concrete RosterEntry rows. Mirrors OrgAssignment's effective-dating."""

    __tablename__ = "weekly_off_patterns"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    weekday = Column(Integer, nullable=False)  # 0=Monday .. 6=Sunday

    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])


class RosterEntry(Base):
    """One row per (episode, date) - the calendar-based source of truth
    for duty allocation, weekly offs, rest days and double shifts, that
    AttendanceRecord reconciles against."""

    __tablename__ = "roster_entries"
    __table_args__ = (UniqueConstraint("episode_id", "date", name="uq_roster_entry_episode_date"),)

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    date = Column(Date, nullable=False)
    shift_id = Column(Integer, ForeignKey("shift_masters.id"), nullable=True)
    second_shift_id = Column(Integer, ForeignKey("shift_masters.id"), nullable=True)  # double shift
    is_weekly_off = Column(Boolean, default=False)
    is_rest_day = Column(Boolean, default=False)
    is_holiday = Column(Boolean, default=False)
    remarks = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])
    shift = relationship("ShiftMaster", foreign_keys=[shift_id])
    second_shift = relationship("ShiftMaster", foreign_keys=[second_shift_id])


class AttendanceRecord(Base):
    """One row per (episode, date) - actual attendance, reconciled
    against RosterEntry."""

    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("episode_id", "date", name="uq_attendance_record_episode_date"),)

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    date = Column(Date, nullable=False)
    shift_id = Column(Integer, ForeignKey("shift_masters.id"), nullable=True)
    check_in = Column(DateTime, nullable=True)
    check_out = Column(DateTime, nullable=True)
    status = Column(String(20), default="PRESENT")  # PRESENT/ABSENT/HALF_DAY/ON_LEAVE/WEEKLY_OFF/HOLIDAY
    late_minutes = Column(Integer, default=0)
    early_departure_minutes = Column(Integer, default=0)
    overtime_minutes = Column(Integer, default=0)
    source = Column(String(20), default="MANUAL")  # MANUAL/CORRECTION
    remarks = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])
    shift = relationship("ShiftMaster", foreign_keys=[shift_id])


class AttendanceException(Base):
    """LATE / EARLY_DEPARTURE / MISSED_PUNCH / ABSENT_UNPLANNED flags
    raised against a day's attendance."""

    __tablename__ = "attendance_exceptions"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    date = Column(Date, nullable=False)
    exception_type = Column(String(30), nullable=False)
    status = Column(String(20), default="OPEN")  # OPEN/RESOLVED
    resolution_remarks = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])


class AttendanceApprovalRequest(Base):
    """Attendance correction + overtime approval, typed by request_type -
    one shared table rather than two, mirrors ChangeRequest's single-table
    design for identity/employment edits."""

    __tablename__ = "attendance_approval_requests"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    date = Column(Date, nullable=False)
    request_type = Column(String(20), nullable=False)  # CORRECTION/OVERTIME
    requested_check_in = Column(DateTime, nullable=True)
    requested_check_out = Column(DateTime, nullable=True)
    requested_overtime_minutes = Column(Integer, nullable=True)
    reason = Column(String(255), nullable=True)
    status = Column(String(20), default="PENDING")  # PENDING/APPROVED/REJECTED
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_remarks = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])


# ---------------------------------------------------------------------------
# Module 2: Leave (blueprint §23)
# ---------------------------------------------------------------------------

class LeaveType(Base):
    """Admin-configurable leave type master (Casual/Sick/Earned etc.)."""

    __tablename__ = "leave_types"

    id = Column(Integer, primary_key=True)
    code = Column(String(30), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    is_paid = Column(Boolean, default=True)
    accrual_frequency = Column(String(20), default="NONE")  # MONTHLY/YEARLY/NONE
    accrual_amount = Column(Float, default=0)
    max_balance = Column(Float, nullable=True)
    carry_forward_limit = Column(Float, nullable=True)
    requires_approval = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class LeaveEligibilityRule(Base):
    """Which employees are entitled to a LeaveType and how much - matched
    cost_center+category -> cost_center-only -> category-only -> global
    fallback, same specificity cascade as approval_service.find_approval_rule."""

    __tablename__ = "leave_eligibility_rules"

    id = Column(Integer, primary_key=True)
    leave_type_id = Column(Integer, ForeignKey("leave_types.id"), nullable=False)
    employee_category_id = Column(Integer, ForeignKey("employee_categories.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    min_service_months = Column(Integer, default=0)
    annual_entitlement = Column(Float, nullable=False)
    created_at = Column(DateTime, default=now)

    leave_type = relationship("LeaveType")
    employee_category = relationship("EmployeeCategory")
    cost_center = relationship("CostCenter")


class LeaveBalance(Base):
    """Per (episode, leave_type, year) balance - accrual computed lazily
    on read, no scheduler in this codebase."""

    __tablename__ = "leave_balances"
    __table_args__ = (UniqueConstraint("episode_id", "leave_type_id", "year", name="uq_leave_balance_episode_type_year"),)

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    leave_type_id = Column(Integer, ForeignKey("leave_types.id"), nullable=False)
    year = Column(Integer, nullable=False)
    opening_balance = Column(Float, default=0)
    accrued = Column(Float, default=0)
    used = Column(Float, default=0)
    adjusted = Column(Float, default=0)
    updated_at = Column(DateTime, default=now, onupdate=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])
    leave_type = relationship("LeaveType")


class LeaveApplication(Base):
    """Leave application - balance deduction happens on approval, not on
    apply, mirroring how OrgAssignment only closes/opens on the actual
    state change."""

    __tablename__ = "leave_applications"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    leave_type_id = Column(Integer, ForeignKey("leave_types.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_half_day = Column(Boolean, default=False)
    half_day_session = Column(String(20), nullable=True)  # FIRST_HALF/SECOND_HALF
    days = Column(Float, nullable=False)
    reason = Column(String(255), nullable=True)
    status = Column(String(20), default="PENDING")  # PENDING/APPROVED/REJECTED/CANCELLED
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_remarks = Column(String(255), nullable=True)
    attachment_object_key = Column(String(500), nullable=True)
    attachment_file_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])
    leave_type = relationship("LeaveType")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])


class HolidayCalendar(Base):
    """Holiday master - cost_center_id null means global/applies to all."""

    __tablename__ = "holiday_calendar"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    date = Column(Date, nullable=False)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    is_optional = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)

    cost_center = relationship("CostCenter")


# ---------------------------------------------------------------------------
# Module 3: Payroll (blueprint §23)
# ---------------------------------------------------------------------------

class SalaryComponent(Base):
    """Admin-configurable salary component master (Basic/HRA/PF/ESI etc.).
    is_statutory rows (PF/ESI/PT/LWF/employer contributions) are computed
    by the statutory engine at payroll-processing time rather than taken
    from SalaryStructureComponent's amount/percentage. `formula` is a
    simpleeval expression used when default_calculation="FORMULA" - it
    may reference other components by code (resolved via a multi-pass
    dependency solve, so e.g. HRA="BASIC*0.4" or GROSS="BASIC+HRA+CONVEYANCE"
    both work) and the day-count variables computed by
    payroll_service.compute_day_variables (PRESENT, ABSENT, HALF_DAY,
    ON_LEAVE, WEEKLY_OFF, HOLIDAY, LATE_DAYS, EARLY_DEP_DAYS, OT_MIN,
    NOT_MARKED), e.g. "BASIC * PRESENT / 30"."""

    __tablename__ = "salary_components"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    component_type = Column(String(30), nullable=False)  # EARNING/DEDUCTION/EMPLOYER_CONTRIBUTION
    default_calculation = Column(String(30), default="FIXED")  # FIXED/PERCENTAGE_OF_BASIC/FORMULA
    default_value = Column(Float, default=0)
    formula = Column(String(500), nullable=True)
    sequence = Column(Integer, default=0)
    is_statutory = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class SalaryStructureComponent(Base):
    """Effective-dated per-component salary assignment - same close-prior-
    row pattern as OrgAssignment/CostAllocation, but per component instead
    of a whole-template switch."""

    __tablename__ = "salary_structure_components"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    component_id = Column(Integer, ForeignKey("salary_components.id"), nullable=False)
    amount = Column(Float, nullable=True)
    percentage = Column(Float, nullable=True)  # for PERCENTAGE_OF_BASIC components
    formula = Column(String(500), nullable=True)  # per-employee override of the component's default formula

    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])
    component = relationship("SalaryComponent")


class SalaryComponentOverride(Base):
    """One-month override of a recurring SalaryStructureComponent's value
    (e.g. Group Insurance is normally Rs.50/month but wasn't collected
    this month - override it to 0 for just this episode+month instead of
    closing/reopening the effective-dated structure row). When present
    for (episode_id, component_id, year, month), payroll processing uses
    `amount` as-is - no proration, no fallback to the structure value."""

    __tablename__ = "salary_component_overrides"
    __table_args__ = (UniqueConstraint("episode_id", "component_id", "year", "month", name="uq_salary_override_episode_component_period"),)

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    component_id = Column(Integer, ForeignKey("salary_components.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    remarks = Column(String(255), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])
    component = relationship("SalaryComponent")
    created_by = relationship("User", foreign_keys=[created_by_id])


class SalaryTemplate(Base):
    """Reusable salary structure blueprint (e.g. "Bus Driver - Standard"),
    scoped to a Cost Center and/or Project, or global when both are null.
    Loading a template into an employee's structure copies its component
    rows as a starting point - the loaded values are then freely editable
    before being applied via set_salary_structure_component, same as any
    manually-entered structure component."""

    __tablename__ = "salary_templates"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)  # null = any Cost Center
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)  # null = any Project (within the Cost Center, if set)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    cost_center = relationship("CostCenter")
    project = relationship("Project")
    components = relationship("SalaryTemplateComponent", back_populates="template", cascade="all, delete-orphan")


class SalaryTemplateComponent(Base):
    """One line item within a SalaryTemplate - mirrors
    SalaryStructureComponent's amount/percentage shape but isn't itself
    effective-dated (the template is a static blueprint; dating only
    matters once it's applied to a specific employee's structure)."""

    __tablename__ = "salary_template_components"
    __table_args__ = (UniqueConstraint("template_id", "component_id", name="uq_salary_template_component"),)

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("salary_templates.id"), nullable=False)
    component_id = Column(Integer, ForeignKey("salary_components.id"), nullable=False)
    amount = Column(Float, nullable=True)
    percentage = Column(Float, nullable=True)
    formula = Column(String(500), nullable=True)

    template = relationship("SalaryTemplate", back_populates="components")
    component = relationship("SalaryComponent")


class StatutoryConfig(Base):
    """Effective-dated, one active row at a time (mirrors OrgAssignment's
    "close prior row" pattern) - admin-configurable PF/ESI/EPS rates and
    wage ceilings, gratuity's statutory constants, and LWF amount/frequency."""

    __tablename__ = "statutory_configs"

    id = Column(Integer, primary_key=True)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)

    pf_employee_rate = Column(Float, default=0.12)
    pf_employer_rate = Column(Float, default=0.12)
    pf_wage_ceiling = Column(Float, default=15000)
    eps_rate = Column(Float, default=0.0833)
    eps_wage_ceiling = Column(Float, default=15000)
    esi_employee_rate = Column(Float, default=0.0075)
    esi_employer_rate = Column(Float, default=0.0325)
    esi_wage_ceiling = Column(Float, default=21000)
    gratuity_days_per_year = Column(Integer, default=15)
    gratuity_divisor = Column(Integer, default=26)
    lwf_employee_amount = Column(Float, default=0)
    lwf_employer_amount = Column(Float, default=0)
    lwf_frequency = Column(String(20), default="MONTHLY")  # MONTHLY/HALF_YEARLY/YEARLY

    created_at = Column(DateTime, default=now)


class ProfessionalTaxSlab(Base):
    """State-specific PT slabs - varies by state and changes independently
    of the other statutory schemes, so HR configures the actual figures
    for their state(s) rather than the plan guessing them (left unseeded)."""

    __tablename__ = "professional_tax_slabs"

    id = Column(Integer, primary_key=True)
    state = Column(String(100), nullable=False)
    min_gross = Column(Float, default=0)
    max_gross = Column(Float, nullable=True)  # null = no upper bound
    monthly_amount = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class PayrollRun(Base):
    """One payroll batch per (cost_center, year, month) -
    DRAFT -> PROCESSED -> APPROVED -> LOCKED. cost_center_id null = all
    cost centers in one run."""

    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("cost_center_id", "year", "month", name="uq_payroll_run_cc_year_month"),)

    id = Column(Integer, primary_key=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    status = Column(String(20), default="DRAFT")  # DRAFT/PROCESSED/APPROVED/LOCKED
    processed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    locked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)

    cost_center = relationship("CostCenter")
    processed_by = relationship("User", foreign_keys=[processed_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])


class Payslip(Base):
    """One payslip per (run, episode) - earned days + gross/net summary.
    Line-item detail lives in PayslipLine; cost-center split in
    PayslipCostSplit."""

    __tablename__ = "payslips"
    __table_args__ = (UniqueConstraint("run_id", "episode_id", name="uq_payslip_run_episode"),)

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("payroll_runs.id"), nullable=False)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)

    present_days = Column(Float, default=0)
    paid_leave_days = Column(Float, default=0)
    lop_days = Column(Float, default=0)  # loss of pay / unpaid

    gross_earnings = Column(Float, default=0)
    gross_deductions = Column(Float, default=0)
    net_pay = Column(Float, default=0)
    employer_cost_total = Column(Float, default=0)
    # ADDITION-type components (bonus, monthly performance/attendance pay
    # etc.) - added to what's actually paid out, but deliberately kept out
    # of gross_earnings/net_pay so they never inflate the PF/ESI wage base
    # (which is computed off gross_earnings). total_payable is the real
    # disbursed amount: net_pay + additional_pay.
    additional_pay = Column(Float, default=0)
    total_payable = Column(Float, default=0)

    generated_at = Column(DateTime, default=now)

    run = relationship("PayrollRun")
    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])


class PayslipLine(Base):
    """One line per salary component on a payslip (earning/deduction/
    employer contribution amount, snapshotted at generation time)."""

    __tablename__ = "payslip_lines"

    id = Column(Integer, primary_key=True)
    payslip_id = Column(Integer, ForeignKey("payslips.id"), nullable=False)
    component_code = Column(String(50), nullable=False)
    component_name = Column(String(150), nullable=False)
    component_type = Column(String(30), nullable=False)
    amount = Column(Float, default=0)

    payslip = relationship("Payslip")


class PayslipCostSplit(Base):
    """Splits a payslip's gross cost across cost-center/project using the
    episode's active CostAllocation percentages as of that month - no new
    allocation concept invented, reuses CostAllocation directly."""

    __tablename__ = "payslip_cost_splits"

    id = Column(Integer, primary_key=True)
    payslip_id = Column(Integer, ForeignKey("payslips.id"), nullable=False)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    percentage = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)

    payslip = relationship("Payslip")
    cost_center = relationship("CostCenter")
    project = relationship("Project")


class AdhocPayEntry(Base):
    """One-off earning/deduction for a specific (episode, year, month),
    rolled into that month's Payslip alongside the recurring structure."""

    __tablename__ = "adhoc_pay_entries"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    label = Column(String(150), nullable=False)
    amount = Column(Float, nullable=False)
    is_earning = Column(Boolean, default=True)
    remarks = Column(String(255), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])
    created_by = relationship("User", foreign_keys=[created_by_id])


class FullFinalSettlement(Base):
    """Payroll-side Full & Final Settlement, computed at separation - one
    row per episode. status reuses the existing FullFinalStatus enum's
    string values (PENDING/IN_PROGRESS/COMPLETED), not redefined here."""

    __tablename__ = "full_final_settlements"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=False, unique=True)
    separation_id = Column(Integer, ForeignKey("separation_records.id"), nullable=True)

    leave_encashment_days = Column(Float, default=0)
    leave_encashment_amount = Column(Float, default=0)
    gratuity_years_of_service = Column(Float, default=0)
    gratuity_amount = Column(Float, default=0)
    notice_pay_recovery = Column(Float, default=0)
    other_dues = Column(Float, default=0)
    net_payable = Column(Float, default=0)
    status = Column(String(20), default="PENDING")  # PENDING/IN_PROGRESS/COMPLETED (FullFinalStatus)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)

    episode = relationship("EmploymentEpisode", foreign_keys=[episode_id])
    separation = relationship("SeparationRecord", foreign_keys=[separation_id])


# ---------------------------------------------------------------------------
# Module 4: Statutory Compliance (blueprint §23)
# ---------------------------------------------------------------------------

class ComplianceRecord(Base):
    """Per (scheme, cost_center, year, month) aggregation of that period's
    PayslipLine amounts for the given scheme - Module 4 aggregates
    already-computed payroll lines rather than recomputing them."""

    __tablename__ = "compliance_records"

    id = Column(Integer, primary_key=True)
    scheme = Column(String(20), nullable=False)  # PF/ESI/PT/GRATUITY/LWF
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)

    total_employee_contribution = Column(Float, default=0)
    total_employer_contribution = Column(Float, default=0)
    employees_covered = Column(Integer, default=0)
    status = Column(String(20), default="PENDING")  # PENDING/FILED/PAID
    challan_reference_number = Column(String(100), nullable=True)
    filed_date = Column(Date, nullable=True)
    remarks = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    cost_center = relationship("CostCenter")


# ---------------------------------------------------------------------------
# Module 5: Recruitment
# ---------------------------------------------------------------------------

class SelectionCriteria(Base):
    """Master list of selection-process stages/tests (e.g. "Govt Steering
    Test", "GCM Medical Test") - admin-configurable, same master-data
    pattern as Designation/EmployeeCategory."""

    __tablename__ = "selection_criteria"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class DesignationCriteria(Base):
    """Which SelectionCriteria a Designation requires to pass before a
    candidate can be converted to an employee. cost_center_id is nullable
    - a null row applies to the designation everywhere (global), a
    non-null row applies only within that Cost Center and is more
    specific - same most-specific-first cascade idea as
    LeaveEligibilityRule/ApprovalRule (see
    recruitment_service.required_criteria)."""

    __tablename__ = "designation_criteria"
    __table_args__ = (UniqueConstraint("designation_id", "cost_center_id", "criteria_id", name="uq_designation_criteria"),)

    id = Column(Integer, primary_key=True)
    designation_id = Column(Integer, ForeignKey("designations.id"), nullable=False)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    criteria_id = Column(Integer, ForeignKey("selection_criteria.id"), nullable=False)
    is_mandatory = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)

    designation = relationship("Designation")
    cost_center = relationship("CostCenter")
    criteria = relationship("SelectionCriteria")


class Candidate(Base):
    """A potential employee, tracked by reference_number rather than an
    employee_number/Employee row - no Employee/EmploymentEpisode exists
    for a candidate until conversion (see
    recruitment_service.convert_to_employee). Deliberately a much
    smaller field set than Employee - only what's needed to run the
    selection process and pre-fill the wizard on conversion."""

    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True)
    # Nullable at the DB level only because it's derived from the row's own
    # id (recruitment_service.generate_reference_number) and so can't be
    # known until after the initial insert/flush - the router always sets
    # it in the same request before commit, so it's never actually null
    # once a caller can see the row.
    reference_number = Column(String(50), unique=True, nullable=True)

    first_name = Column(String(100), nullable=False)
    middle_name = Column(String(100))
    last_name = Column(String(100), nullable=False)
    father_husband_name = Column(String(255))
    gender = Column(String(20))
    date_of_birth = Column(Date)
    mobile_number = Column(String(20))
    alternate_mobile_number = Column(String(20))
    personal_email = Column(String(255))
    educational_qualification = Column(String(255))
    # Mirrors Employee's "Previous Experience" section, but named "current"
    # here since a candidate's employer at application time is their
    # CURRENT one - it only becomes their "previous" employer once they're
    # converted (see recruitment_service.convert_to_employee, which maps
    # these onto Employee.previous_designation/previous_company_name/
    # previous_company_details/previous_date_of_joining).
    current_designation = Column(String(150))
    current_company_name = Column(String(255))
    current_company_details = Column(Text)
    current_date_of_joining = Column(Date)
    total_experience_years = Column(Float)
    # Identity Documents subsection - Name/DOB as printed on the card
    # alongside the Number, same shape as Employee's own Aadhaar/PAN
    # fields, copied over verbatim on conversion
    # (recruitment_service.convert_to_employee).
    # Checked for duplicates against both Employee.aadhaar and other
    # candidates' aadhaar on create/update - see
    # recruitment_service.check_aadhaar_duplicates. A match is surfaced as
    # a warning, never a hard block (the same person could legitimately be
    # re-applying, or it could be a data-entry mistake HR needs to see and
    # judge, not one the system should silently prevent).
    aadhaar = Column(String(20))
    aadhaar_name = Column(String(255))
    aadhaar_dob = Column(Date)
    pan = Column(String(20))
    pan_name = Column(String(255))
    pan_dob = Column(Date)

    # Driving Licence - shown/required based on the same
    # DrivingLicenceRequirement rules (Employee Category/Designation) used
    # for employees, matched against the candidate's applied Category/
    # Designation (see services/licence_service.py::
    # resolve_driving_licence_requirement_for_candidate). Flattened onto
    # Candidate rather than a separate table since it's one row per
    # candidate, same reasoning as Current Experience above. Copied into a
    # DrivingLicenceDetail row for the new episode on conversion.
    dl_licence_number = Column(String(50))
    dl_badge_number = Column(String(50))
    dl_vehicle_class = Column(String(100))
    dl_issuing_authority = Column(String(255))
    dl_issue_date = Column(Date)
    dl_expiry_date = Column(Date)

    applied_designation_id = Column(Integer, ForeignKey("designations.id"), nullable=False)
    applied_employee_category_id = Column(Integer, ForeignKey("employee_categories.id"), nullable=True)
    applied_cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=False)
    applied_project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    # Legacy - Organizational Assignment for a candidate only ever captured
    # Cost Center + Project (Department is decided later, during the
    # post-conversion wizard); kept only because migrate.py never drops
    # columns, no longer read or written.
    applied_department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)

    applied_date = Column(Date, default=dt.date.today)
    source = Column(String(150))
    status = Column(String(20), default="APPLIED")  # CandidateStatus
    remarks = Column(Text)

    converted_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    converted_episode_id = Column(Integer, ForeignKey("employment_episodes.id"), nullable=True)

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    designation = relationship("Designation")
    employee_category = relationship("EmployeeCategory")
    cost_center = relationship("CostCenter")
    project = relationship("Project")
    department = relationship("Department")
    stage_results = relationship("CandidateStageResult", back_populates="candidate", cascade="all, delete-orphan")
    salary_components = relationship("CandidateSalaryComponent", back_populates="candidate", cascade="all, delete-orphan")
    documents = relationship("CandidateDocument", back_populates="candidate", cascade="all, delete-orphan")


class CandidateStageResult(Base):
    """One row per (candidate, criteria) - the candidate's result for that
    selection stage. Starts absent (treated as PENDING) until HR records a
    result; recruitment_service.required_criteria + this table together
    answer "has this candidate passed everything their designation
    requires". Carries one optional proof-of-completion attachment (e.g. a
    scanned test result/certificate) - single-attachment-per-row, same
    convention as LeaveApplication's supporting document (see
    services/recruitment_service.py::save_stage_result_attachment)."""

    __tablename__ = "candidate_stage_results"
    __table_args__ = (UniqueConstraint("candidate_id", "criteria_id", name="uq_candidate_stage_result"),)

    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    criteria_id = Column(Integer, ForeignKey("selection_criteria.id"), nullable=False)
    result = Column(String(20), default="PENDING")  # PENDING/PASS/FAIL
    tested_on = Column(Date, nullable=True)
    remarks = Column(String(500), nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    attachment_object_key = Column(String(500), nullable=True)
    attachment_file_name = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=now, onupdate=now)

    candidate = relationship("Candidate", back_populates="stage_results")
    criteria = relationship("SelectionCriteria")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])


class CandidateSalaryComponent(Base):
    """The salary HR sets for a candidate once selection clears, held here
    (not yet effective-dated - there's no episode to date it against
    until conversion) and copied verbatim into SalaryStructureComponent
    rows by recruitment_service.convert_to_employee, using the same
    set_salary_structure_component this codebase already uses everywhere
    else for that table."""

    __tablename__ = "candidate_salary_components"

    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    component_id = Column(Integer, ForeignKey("salary_components.id"), nullable=False)
    amount = Column(Float, nullable=True)
    percentage = Column(Float, nullable=True)
    formula = Column(String(500), nullable=True)

    candidate = relationship("Candidate", back_populates="salary_components")
    component = relationship("SalaryComponent")


class CandidateDocument(Base):
    """One row per (candidate, DocumentType) uploaded during recruitment -
    same shape/convention as DocumentMeta (episode-scoped documents), but
    for a Candidate that has no episode yet. Which DocumentTypes are
    required is NOT configured separately for recruitment - it reuses the
    exact same DocumentRequirement rules (scoped by Employee Category/
    Designation) that already drive the Documents step of the Employee
    wizard, matched against the candidate's applied designation/category
    (see services/document_service.py::resolve_required_documents_for_candidate).
    On conversion, these are copied into DocumentMeta rows for the new
    episode so the candidate never has to re-upload (see
    services/document_service.py::copy_candidate_documents_to_episode)."""

    __tablename__ = "candidate_documents"

    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    document_type_id = Column(Integer, ForeignKey("document_types.id"), nullable=True)

    document_type = Column(String(100), nullable=False)  # denormalized DocumentType.name snapshot
    file_name = Column(String(500))
    object_key = Column(String(500))
    file_size = Column(Integer)
    mime_type = Column(String(100))
    version = Column(Integer, default=1)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    verification_status = Column(String(20), default="PENDING")
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    candidate = relationship("Candidate", back_populates="documents")
    document_type_rel = relationship("DocumentType")
    uploaded_by = relationship("User")


class CandidateChangeRequest(Base):
    """Approval-workflow record for edits to (or a document deletion on)
    an already-APPROVED Candidate - "approved data must not be
    overwritten directly," the same principle blueprint §15 applies to an
    ACTIVE EmploymentEpisode via ChangeRequest, ported here as a
    dedicated table rather than widening the Module 1 ChangeRequest table
    (whose episode_id column is NOT NULL and tightly coupled to
    EmploymentEpisode). changes_json/previous_values_json hold a JSON
    dict, same shape as ChangeRequest - for request_type=FIELD_CHANGE it's
    field->value; for request_type=DOCUMENT_DELETE it's just
    {"document_id": ...} (nothing to "apply" but the deletion itself, done
    on approval - see recruitment_service.review_candidate_change_request)."""

    __tablename__ = "candidate_change_requests"

    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    request_type = Column(String(20), nullable=False)  # FIELD_CHANGE / DOCUMENT_DELETE
    changes_json = Column(Text)
    previous_values_json = Column(Text)
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_remarks = Column(Text)
    status = Column(String(20), default="PENDING")
    created_at = Column(DateTime, default=now)

    candidate = relationship("Candidate")
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
