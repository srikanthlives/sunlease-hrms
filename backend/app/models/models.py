import datetime as dt

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text,
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
    departments = relationship("Department", back_populates="cost_center")


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
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=False)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    cost_center = relationship("CostCenter", back_populates="departments")


class EmployeeCategory(Base):
    """Admin-configurable, per blueprint §13 - not hard-coded."""

    __tablename__ = "employee_categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class WorkLocation(Base):
    """Admin-configurable, linked to a Project (each Project's site(s))."""

    __tablename__ = "work_locations"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(150), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    project = relationship("Project")


class Designation(Base):
    """Admin-configurable job title master (e.g. Bus Driver, Conductor,
    Site Supervisor) - not hard-coded, same pattern as EmployeeCategory."""

    __tablename__ = "designations"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


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
    aadhaar = Column(String(20))
    pan = Column(String(20))
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
