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
    # A distinct role above HR_ADMIN, exclusively for the database
    # backup/restore tools (core/deps.py::require_super_admin,
    # routers/admin.py) - a superset of HR_ADMIN everywhere HR_ADMIN is
    # allowed (see require_permission's bypass check), but HR_ADMIN itself
    # cannot reach db-backup/db-restore. Mirrors sunlease-expms's
    # SUPER_ADMIN role.
    SUPER_ADMIN = "SUPER_ADMIN"

    ALL = [HR_ADMIN, HR_STAFF, APPROVER, EMPLOYEE, SUPER_ADMIN]


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


class CandidateStatus:
    # Freely, directly editable - HR is still entering/correcting data.
    APPLIED = "APPLIED"
    # Submitted for the initial approval an APPROVER/HR_ADMIN must grant
    # before Selection Criteria can be recorded - mirrors EmploymentEpisode's
    # DRAFT -> PENDING_APPROVAL -> ACTIVE cascade (routed through the same
    # ApprovalRule-matching idea, see
    # recruitment_service.authorize_candidate_approval).
    PENDING_APPROVAL = "PENDING_APPROVAL"
    # Set once that initial approval is granted. From here: Selection
    # Criteria stage results can be recorded, and any further edit to the
    # candidate's own details (or a document deletion) must go through a
    # CandidateChangeRequest instead of applying directly - "approved data
    # must not be overwritten directly," same principle as an ACTIVE
    # EmploymentEpisode (blueprint §15).
    APPROVED = "APPROVED"
    # Terminal - HR/Approver has disqualified this candidate outright (see
    # /candidates/{id}/disqualify), distinct from PENDING_APPROVAL being
    # sent back to APPLIED for correction (see /candidates/{id}/reject).
    REJECTED = "REJECTED"
    CONVERTED = "CONVERTED"
    WITHDRAWN = "WITHDRAWN"

    ALL = [APPLIED, PENDING_APPROVAL, APPROVED, REJECTED, CONVERTED, WITHDRAWN]


class CriteriaResult:
    PENDING = "PENDING"
    PASS_ = "PASS"
    FAIL = "FAIL"

    ALL = [PENDING, PASS_, FAIL]


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

    # Module 2: Attendance + Leave (blueprint §23)
    ATTENDANCE_VIEW = "attendance.view"
    ATTENDANCE_MARK = "attendance.mark"
    ROSTER_MANAGE = "roster.manage"
    ATTENDANCE_CORRECT = "attendance.correct"
    ATTENDANCE_APPROVE = "attendance.approve"
    LEAVE_APPLY = "leave.apply"
    LEAVE_APPROVE = "leave.approve"
    LEAVE_ADMIN = "leave.admin"

    # Module 3/4: Payroll + Statutory Compliance
    PAYROLL_VIEW = "payroll.view"
    PAYROLL_PROCESS = "payroll.process"
    PAYROLL_APPROVE = "payroll.approve"
    PAYROLL_LOCK = "payroll.lock"
    PAYSLIP_VIEW = "payslip.view"
    FNF_PROCESS = "fnf.process"
    COMPLIANCE_VIEW = "compliance.view"
    COMPLIANCE_FILE = "compliance.file"

    # Module 5: Recruitment
    RECRUITMENT_VIEW = "recruitment.view"
    RECRUITMENT_MANAGE = "recruitment.manage"

    ALL = [
        EMPLOYEE_VIEW, EMPLOYEE_CREATE, EMPLOYEE_EDIT, EMPLOYEE_APPROVE, EMPLOYEE_SEPARATE,
        EMPLOYEE_SENSITIVE_VIEW, EMPLOYEE_SENSITIVE_EDIT,
        EMPLOYEE_DOCUMENTS_VIEW, EMPLOYEE_DOCUMENTS_UPLOAD,
        CHANGE_REQUESTS_REVIEW, ORG_MANAGE, USERS_MANAGE, AUDIT_VIEW,
        ATTENDANCE_VIEW, ATTENDANCE_MARK, ROSTER_MANAGE, ATTENDANCE_CORRECT,
        ATTENDANCE_APPROVE, LEAVE_APPLY, LEAVE_APPROVE, LEAVE_ADMIN,
        PAYROLL_VIEW, PAYROLL_PROCESS, PAYROLL_APPROVE, PAYROLL_LOCK,
        PAYSLIP_VIEW, FNF_PROCESS, COMPLIANCE_VIEW, COMPLIANCE_FILE,
        RECRUITMENT_VIEW, RECRUITMENT_MANAGE,
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
            # Module 2: HR_STAFF runs roster/attendance day to day and
            # administers leave configuration.
            ATTENDANCE_VIEW, ATTENDANCE_MARK, ROSTER_MANAGE, ATTENDANCE_CORRECT,
            LEAVE_APPLY, LEAVE_ADMIN,
            # Module 3/4: HR_STAFF runs payroll processing, ad-hoc entries,
            # full & final settlement, and compliance filing day to day.
            # PAYROLL_LOCK is deliberately excluded - HR_ADMIN-only.
            PAYROLL_VIEW, PAYROLL_PROCESS, PAYSLIP_VIEW, FNF_PROCESS,
            COMPLIANCE_VIEW, COMPLIANCE_FILE,
            # Module 5: HR_STAFF runs the recruitment pipeline day to day,
            # including converting a selected candidate to an employee.
            RECRUITMENT_VIEW, RECRUITMENT_MANAGE,
        ],
        RoleName.APPROVER: [
            EMPLOYEE_VIEW, EMPLOYEE_APPROVE, EMPLOYEE_SENSITIVE_VIEW,
            CHANGE_REQUESTS_REVIEW, AUDIT_VIEW,
            # Module 2: APPROVER reviews attendance corrections/overtime
            # and leave applications.
            ATTENDANCE_VIEW, ATTENDANCE_APPROVE, LEAVE_APPROVE,
            # Module 3/4: APPROVER reviews/approves payroll runs and views
            # compliance records, but does not process or lock.
            PAYROLL_VIEW, PAYROLL_APPROVE, PAYSLIP_VIEW, COMPLIANCE_VIEW,
            RECRUITMENT_VIEW,
        ],
        RoleName.EMPLOYEE: [
            # Module 2: EMPLOYEE can view their own attendance and apply
            # for leave (self-service login itself is still deferred).
            ATTENDANCE_VIEW, LEAVE_APPLY,
            # Module 3: EMPLOYEE can view their own payslips.
            PAYSLIP_VIEW,
        ],
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

    # Module 2: Attendance + Leave (blueprint §23)
    ATTENDANCE_CORRECTION = "ATTENDANCE_CORRECTION"
    OVERTIME_APPROVAL = "OVERTIME_APPROVAL"
    LEAVE_APPLICATION = "LEAVE_APPLICATION"

    # Module 3: Payroll (blueprint §23)
    PAYROLL_PROCESSING = "PAYROLL_PROCESSING"

    # Module 5: Recruitment - initial candidate approval (gates Selection
    # Criteria recording) and edits/document-deletions on an
    # already-APPROVED candidate (recruitment_service.py).
    RECRUITMENT_APPROVAL = "RECRUITMENT_APPROVAL"
    RECRUITMENT_CHANGE = "RECRUITMENT_CHANGE"

    ALL = [
        EMPLOYEE_CREATION, IDENTITY_CHANGE, EMPLOYMENT_CHANGE, ORG_CHANGE,
        BANK_CHANGE, STATUTORY_CHANGE, SEPARATION, DOCUMENT_CHANGE,
        ATTENDANCE_CORRECTION, OVERTIME_APPROVAL, LEAVE_APPLICATION,
        PAYROLL_PROCESSING, RECRUITMENT_APPROVAL, RECRUITMENT_CHANGE,
    ]
