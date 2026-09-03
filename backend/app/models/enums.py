"""Plain string constants used as 'status'/'type' values.

SQLite has no native enum type and enum migrations are painful, so these
are stored as plain strings (validated at the Pydantic/service layer)
rather than DB-level enums. Keeps the schema easy to extend for later
HRMS modules (Attendance, Payroll, Compliance) without an Alembic
enum-altering migration.
"""


class RoleName:
    HR_ADMIN = "HR_ADMIN"
    HR_STAFF = "HR_STAFF"
    APPROVER = "APPROVER"
    EMPLOYEE = "EMPLOYEE"

    ALL = [HR_ADMIN, HR_STAFF, APPROVER, EMPLOYEE]


class EpisodeStatus:
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    NOTICE_PERIOD = "NOTICE_PERIOD"
    SEPARATED = "SEPARATED"


class AddressType:
    PRESENT = "PRESENT"
    PERMANENT = "PERMANENT"


class Gender:
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class MaritalStatus:
    SINGLE = "SINGLE"
    MARRIED = "MARRIED"
    OTHER = "OTHER"


class EmploymentType:
    PERMANENT = "PERMANENT"
    CONTRACT = "CONTRACT"
    PROBATION = "PROBATION"
    APPRENTICE = "APPRENTICE"


class VerificationStatus:
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class NominationType:
    PF = "PF"
    GRATUITY = "GRATUITY"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


class SeparationType:
    RESIGNATION = "RESIGNATION"
    TERMINATION = "TERMINATION"
    ABSCONDING = "ABSCONDING"
    RETIREMENT = "RETIREMENT"
    DEATH = "DEATH"
    CONTRACT_COMPLETION = "CONTRACT_COMPLETION"
    OTHER = "OTHER"


class FullFinalStatus:
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class ChangeRequestStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AuditAction:
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    STATUS_CHANGE = "STATUS_CHANGE"
    LOGIN = "LOGIN"
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class Permission:
    """Granular permission codes (blueprint §18). Checked via
    RolePermission grants - see core/deps.py::require_permission and
    services/permission_service.py. HR_ADMIN implicitly has every code
    (bypass), so it's never seeded with explicit grants."""

    EMPLOYEE_VIEW = "employee.view"
    EMPLOYEE_CREATE = "employee.create"
    EMPLOYEE_EDIT = "employee.edit"
    EMPLOYEE_APPROVE = "employee.approve"
    EMPLOYEE_SEPARATE = "employee.separate"
    EMPLOYEE_SENSITIVE_VIEW = "employee.sensitive.view"    # Aadhaar/PAN/bank/statutory numbers
    EMPLOYEE_SENSITIVE_EDIT = "employee.sensitive.edit"
    EMPLOYEE_DOCUMENTS_VIEW = "employee.documents.view"
    EMPLOYEE_DOCUMENTS_UPLOAD = "employee.documents.upload"
    CHANGE_REQUESTS_REVIEW = "change_requests.review"
    ORG_MANAGE = "org.manage"
    USERS_MANAGE = "users.manage"
    AUDIT_VIEW = "audit.view"

    ALL = [
        EMPLOYEE_VIEW, EMPLOYEE_CREATE, EMPLOYEE_EDIT, EMPLOYEE_APPROVE, EMPLOYEE_SEPARATE,
        EMPLOYEE_SENSITIVE_VIEW, EMPLOYEE_SENSITIVE_EDIT,
        EMPLOYEE_DOCUMENTS_VIEW, EMPLOYEE_DOCUMENTS_UPLOAD,
        CHANGE_REQUESTS_REVIEW, ORG_MANAGE, USERS_MANAGE, AUDIT_VIEW,
    ]

    # Seed-time default grants per role (see seed.py). HR_ADMIN is not
    # listed - it bypasses permission checks entirely.
    DEFAULTS = {
        RoleName.HR_STAFF: [
            EMPLOYEE_VIEW, EMPLOYEE_CREATE, EMPLOYEE_EDIT,
            # HR_STAFF runs the registration wizard end to end, which
            # includes the Statutory/Bank/Driving Licence steps - those
            # write (and re-display) sensitive fields, so both are needed
            # here or a registrar can't get past those steps at all.
            EMPLOYEE_SENSITIVE_VIEW, EMPLOYEE_SENSITIVE_EDIT,
            EMPLOYEE_DOCUMENTS_VIEW, EMPLOYEE_DOCUMENTS_UPLOAD,
            # HR_STAFF also runs the exit flow day to day (blueprint §16).
            EMPLOYEE_SEPARATE,
        ],
        RoleName.APPROVER: [
            EMPLOYEE_VIEW, EMPLOYEE_APPROVE, EMPLOYEE_SENSITIVE_VIEW,
            CHANGE_REQUESTS_REVIEW, AUDIT_VIEW,
        ],
        RoleName.EMPLOYEE: [],
    }


class TransactionType:
    """What kind of change an ApprovalRule or ChangeRequest is routing
    (blueprint §15 - Cost Center + Employee Category + Transaction Type)."""

    EMPLOYEE_CREATION = "EMPLOYEE_CREATION"
    IDENTITY_CHANGE = "IDENTITY_CHANGE"
    EMPLOYMENT_CHANGE = "EMPLOYMENT_CHANGE"
    ORG_CHANGE = "ORG_CHANGE"
    BANK_CHANGE = "BANK_CHANGE"
    STATUTORY_CHANGE = "STATUTORY_CHANGE"
    SEPARATION = "SEPARATION"
    DOCUMENT_CHANGE = "DOCUMENT_CHANGE"

    ALL = [
        EMPLOYEE_CREATION, IDENTITY_CHANGE, EMPLOYMENT_CHANGE, ORG_CHANGE,
        BANK_CHANGE, STATUTORY_CHANGE, SEPARATION, DOCUMENT_CHANGE,
    ]
