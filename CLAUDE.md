# CLAUDE.md — HRMS (Employee Data Management, Module 1)

Context file for continuing work on this project. Read this before making
changes. Structure and conventions deliberately mirror the sibling project
`sunlease-expms` (same author, same stack) — when in doubt about a pattern
not covered here, check how expms does it.

## What this is

Module 1 (Employee Data Management) of a 4-module HRMS, built from
`HRMS_Module_1_Employee_Data_Management_Blueprint.docx` (originally in
`~/Downloads`). The other three modules (Attendance, Payroll, Compliance)
are future work and will read Employee/EmploymentEpisode as their source
of truth rather than keeping their own employee masters.

- Backend: FastAPI + SQLAlchemy + SQLite, at `backend/`
- Frontend: React + Vite + Tailwind (plain JS/JSX, no TypeScript), at `frontend/`
- Source of truth for setup: `README.md` in repo root.

## Core architecture (stable, don't relitigate)

- **Employee vs Employment Episode**: `Employee` is the person (identity
  fields that never change). `EmploymentEpisode` is one stint of
  employment (`employee_number`, dates, status). Rejoining after
  separation creates a **new** `EmploymentEpisode` under the same
  `Employee` — never a new `Employee` row and never a duplicate person
  record. All the wizard/profile/lifecycle endpoints key off
  `episode_id`, not `employee_id`.
- **Effective-dating**: `OrgAssignment`, `CostAllocation`,
  `StatutoryInfo`, `BankAccount` are all effective-dated
  (`effective_from`/`effective_to`) and historical rows are never
  overwritten. `employee_service.add_org_assignment` closes the
  previously-open assignment's `effective_to` before inserting the new
  row — this is what enforces "one active Department at a time"
  (blueprint §21).
- **Cost allocation vs org assignment are independent** (blueprint §6):
  an employee has exactly one active Department, but can have multiple
  active Cost Center/Project cost allocations. Allocations are expected
  to sum to 100% but this is enforced as a soft check
  (`active_allocation_total`), not a hard block — matches the blueprint's
  "recommended rule" wording.
- **No physical deletes.** Org/employee/master records are deactivated
  (`is_active=False`) or transitioned to a terminal status
  (`SEPARATED`), never deleted.
- `AuditLog` gets an append-only row for every create/update/status-change
  action, written via `services/audit_service.record()`.

## Roles and RBAC (v2 — blueprint §18)

- **HR_ADMIN** bypasses every permission and Cost Center scope check
  entirely (implicit superuser) — never given explicit `RolePermission`
  rows, checked as a first branch in `core/deps.py::require_permission`,
  `services/permission_service.py`, and
  `services/approval_service.py::authorize_approval`.
- **HR_STAFF**, **APPROVER**, **EMPLOYEE** — granted granular permission
  codes (`models/enums.py::Permission`, e.g. `employee.view`,
  `employee.edit`, `employee.sensitive.view`, `change_requests.review`)
  via the `RolePermission` table. Default grants per role live in
  `Permission.DEFAULTS` and are applied by `seed.py`; HR_ADMIN can also
  edit them live via **Roles & Permissions** in the UI (`PUT
  /roles/{id}/permissions`, full-replace).
- Gate new endpoints with `core/deps.py::require_permission(code)`, not
  hand-rolled role checks — same convention as expms's `require_roles`.
- **Cost Center scoping**: `UserCostCenterScope` restricts which Cost
  Centers a non-HR_ADMIN user can see/act on
  (`services/permission_service.py::can_see_cost_center`,
  `user_cost_center_ids`). An employee record with no `OrgAssignment` yet
  (a fresh draft) is visible to anyone with the base permission — scoping
  only applies once the record is actually assigned somewhere. Zero scope
  rows means zero visibility once assigned (mirrors expms's
  `project_accounts_users` pattern for ACCOUNTS users).
- **Field-level access**: `permission_service.py::mask_sensitive_fields`
  strips Aadhaar/PAN/bank account number+IFSC/statutory numbers (UAN/PF/ESI)
  from `GET /employees/{id}` responses unless the caller has
  `employee.sensitive.view`. Editing those same fields requires
  `employee.sensitive.edit` (`/statutory`, `/bank` endpoints).

## Approval routing + Change Requests (v2 — blueprint §15)

- **`ApprovalRule`** routes an approval to a role (or one specific user)
  by Cost Center + Employee Category + Transaction Type
  (`models/enums.py::TransactionType`). Matched most-specific-first in
  `services/approval_service.py::find_approval_rule`
  (cost_center+category → cost_center-only → category-only → global
  fallback with both null) — same fallback idea as expms's
  `Project.accounts_approver_id`. No matching rule → any `APPROVER` may
  act. `/employees/{id}/approve` and `/reject` (new-employee creation)
  call `authorize_approval(..., TransactionType.EMPLOYEE_CREATION)`
  instead of a flat permission check, since the *who* depends on the
  matched rule, not a static role.
- **`ChangeRequest`** gates edits to an already-**ACTIVE** employee's
  identity (`Employee`) or employment (`EmploymentEpisode`) fields —
  "approved data must not be overwritten directly." The `PUT
  /employees/{id}/personal` and `/employment` endpoints branch in
  `routers/employees.py::_save_or_request`: HR_ADMIN or a non-ACTIVE
  episode → apply directly (as Phase 1 did); otherwise → create a
  `ChangeRequest` and return `{"submitted_for_approval": true}` instead of
  applying. `services/approval_service.py::apply_changes` is the single
  function used by **both** the direct path and
  `review_change_request`'s approve path, so they can never drift apart —
  same pattern as expms's `edit_request_service.apply_changes`.
  **Bank/Statutory/OrgAssignment/CostAllocation are NOT routed through
  ChangeRequest** — they're already effective-dated, append-only rows (a
  "change" there is a new row, never an overwrite of history), so the
  gate doesn't apply to them; only the two entities that support a
  genuine in-place overwrite need it. `TransactionType.BANK_CHANGE` /
  `STATUTORY_CHANGE` / `ORG_CHANGE` exist for `ApprovalRule` routing
  purposes (e.g. future use) but nothing currently creates a
  `ChangeRequest` with those types.
- The `ChangeRequest` table's original Phase 1 columns
  (`entity`/`field_name`/`old_value`/`new_value`) are unused by this flow
  (kept only because `migrate.py` never drops columns) — `changes_json`/
  `previous_values_json` (JSON dict, multi-field per request) are what's
  actually used now, same shape as expms's `EditRequest.changes`.
- Review queue: `GET /employees-change-requests` (HR_STAFF sees only
  their own; anyone with `change_requests.review` or HR_ADMIN sees all),
  `POST .../{id}/approve`, `POST .../{id}/reject` — both call
  `authorize_approval` under the hood with the request's
  `transaction_type`, so the same routing rules apply here as to episode
  approval.

## Phase 1 + v2 scope (what's built) vs still deferred

Built: organization model, Employee + EmploymentEpisode, effective-dated
OrgAssignment + CostAllocation, 8-step Employee Creation Wizard, lifecycle
(Draft → Pending Approval → Active, plus Separation), Employee Profile
360° view, append-only audit log, **plus (v2)** granular RBAC + Cost
Center scoping + field-level sensitive-data masking + a real approval
routing engine + a working ChangeRequest workflow, with admin UI for all
of it (Users & Roles, Roles & Permissions, Approval Rules, Change
Requests pages).

Still deliberately deferred:

- **Cloudflare R2 document upload** — `DocumentMeta` table/schema exists
  (blueprint §14) with a nullable `object_key`, but no actual upload
  endpoint or R2 client wiring yet. `boto3` is already in
  `requirements.txt` for when this gets built.
- **Employee self-service login** (mobile number + 8-digit credential,
  blueprint §19) — not built. The `User.employee_id` column exists for
  this but nothing populates or uses it that way yet.
- **Previous Employment** (blueprint §12) — no model/UI at all yet.
- **Separation approval routing** — `/separate` is permission-gated
  (`employee.separate`) but not routed through `authorize_approval`/
  `ApprovalRule` the way creation and change requests are, and
  `full_final_status` on `SeparationRecord` is still unused pending
  Payroll module integration.

## Testing pattern used throughout this project

**Never `rm -f ../data/hrms.db` as a routine step.** After a model change,
just restart uvicorn — `app/migrate.py` runs automatically on startup and
additively applies the diff (new tables/columns) with zero data loss. Only
reset the database if the user explicitly asks for a clean slate, or a
change needs a rename/retype that `migrate.py` can't do (see its
docstring) — and even then, ask first.

Start uvicorn with:
```bash
nohup uvicorn app.main:app --host 127.0.0.1 --port 8010 > /tmp/hrms_uvicorn.log 2>&1 < /dev/null &
disown
```
in its own tool call (background processes die at tool-call boundaries in
this environment) — start it, then in the *next* tool call curl against
it. Drive tests with `curl` or Python `requests` against the live API,
covering both the happy path and the 401/400/409 guardrails (employee
number uniqueness, invalid status transitions).

After every frontend change: `cd frontend && npm install -q && npm run
build` must succeed with zero errors before considering the change done.

Port 8000 is used by other local projects on this machine (`expms` /
Docker) — this project's backend runs on **8010** in dev
(`frontend/.env.development` points there); don't reuse 8000.

## Seed data

`backend/app/seed.py` creates: all four `RoleName` roles + their default
`RolePermission` grants (`Permission.DEFAULTS`), one HR_ADMIN user
(`admin` / `Admin@123`), one Company ("Sunlease Renewables"), one Cost
Center (`CC-PDY` / Puducherry), one Department (`DEPT-OPS` / Operations),
three Employee Categories (Staff, Worker, Driver), one HR_STAFF user
(`hrstaff` / `HrStaff@123`) and one APPROVER user (`approver` /
`Approver@123`) both scoped to `CC-PDY` via `UserCostCenterScope`, and one
global-fallback `ApprovalRule` (transaction_type=EMPLOYEE_CREATION,
approver_role=APPROVER, cost_center/category=null) — enough for the golden
path (create draft → fill wizard → submit → approve) **and** the full v2
RBAC/approval-routing/change-request flow to be testable immediately after
a fresh seed. Idempotent, safe to re-run.

## Next module

Per the blueprint (§23): **Employee Attendance Management** — shifts,
rosters, duty allocation, weekly offs, rest days, double shifts,
attendance capture, exceptions, leave, attendance corrections, approvals,
overtime, and payroll integration, including bus-operations-specific
requirements. It will consume `Employee`/`EmploymentEpisode` as its
source of truth rather than duplicating employee data (per blueprint §9).
