# CLAUDE.md — HRMS (all 4 modules)

Context file for continuing work on this project. Read this before making
changes. Structure and conventions deliberately mirror the sibling project
`sunlease-expms` (same author, same stack) — when in doubt about a pattern
not covered here, check how expms does it. The sibling `salary-app`
project was also mined for payroll/formula-engine ideas (adapted, not
copied — see Module 3 below for where the design deliberately diverges).

## What this is

A 4-module HRMS built from `HRMS_Module_1_Employee_Data_Management_Blueprint.docx`
(originally in `~/Downloads`). **All four modules are now built**:
Module 1 (Employee Data Management), Module 2 (Attendance + Leave),
Module 3 (Payroll Management), Module 4 (Statutory Compliance). Modules
2–4 all consume `Employee`/`EmploymentEpisode` as their source of truth
rather than keeping their own employee masters, per the blueprint's
design.

- Backend: FastAPI + SQLAlchemy + SQLite, at `backend/`
- Frontend: React + Vite + Tailwind (plain JS/JSX, no TypeScript), at `frontend/`
- Source of truth for setup: `README.md` in repo root.
- Deployed via Docker locally: `docker compose up -d --build` — container
  serves on **port 8020**, backed by a persistent `./data` volume (SQLite
  DB + uploaded attachments). `migrate.py` runs additively on every
  container start, so redeploying never loses data.

## Core architecture (stable, don't relitigate)

- **Employee vs Employment Episode**: `Employee` is the person (identity
  fields that never change). `EmploymentEpisode` is one stint of
  employment (`employee_number`, dates, status). Rejoining after
  separation creates a **new** `EmploymentEpisode` under the same
  `Employee` — never a new `Employee` row and never a duplicate person
  record. Almost every endpoint across all 4 modules keys off
  `episode_id`, not `employee_id`.
- **Effective-dating is the house style for anything that changes over
  time**: `OrgAssignment`, `CostAllocation`, `StatutoryInfo`,
  `BankAccount` (Module 1), `WeeklyOffPattern` (Module 2),
  `SalaryStructureComponent`, `StatutoryConfig` (Module 3) all use
  `effective_from`/`effective_to` and historical rows are never
  overwritten — a "change" is always a new row that closes the prior
  one's `effective_to`. `employee_service.add_org_assignment` and
  `payroll_service.set_salary_structure_component` are the two reference
  implementations of the close-prior-row pattern; the latter also
  **rejects an insert that would overlap an already-open row** (closes
  every open row that starts before the new one, raises if one starts on
  or after it) — this was a real bug found and fixed mid-project (a
  same-day duplicate insert used to leave two rows simultaneously open).
- **Cost allocation vs org assignment are independent** (blueprint §6):
  an employee has exactly one active Department, but can have multiple
  active Cost Center/Project cost allocations (soft-checked to sum to
  100%, not hard-blocked). Payroll's `PayslipCostSplit` reuses these same
  `CostAllocation` percentages to split payroll cost across cost centers
  at processing time.
- **No physical deletes for master/history data.** Org/master records are
  deactivated (`is_active=False`), not deleted — **except** two
  deliberate exceptions added later: (1) master data (Cost Center,
  Project, Department, Employee Category, Work Location, Designation,
  Employee Type) now **hard-deletes if nothing references it yet**,
  falling back to deactivate only if it's actually in use
  (`routers/masters.py::_delete_or_deactivate`); deactivated rows still
  show in their admin list (`?include_inactive=true`) with an Activate
  button. (2) a **DRAFT** employee can be hard-deleted outright
  (`DELETE /employees/{episode_id}`, 400 for any other status) — nothing
  has been approved yet, so there's genuinely nothing to lose. Ad-hoc pay
  entries (`AdhocPayEntry`) and salary component overrides are also
  genuinely deletable — they're one-off, point-in-time corrections, not
  history.
- `AuditLog` gets an append-only row for every create/update/status-change/
  delete action, written via `services/audit_service.record()`.
- **Formula/expression evaluation** (Module 3): `simpleeval`
  (`payroll_service.py`), never raw `eval()` — no Python
  builtins/attributes/imports reachable, only a variable context dict and
  a whitelisted function set. See Module 3 below.

## Roles and RBAC (v2 — blueprint §18)

- **HR_ADMIN** bypasses every permission and Cost Center scope check
  entirely (implicit superuser) — never given explicit `RolePermission`
  rows, checked as a first branch in `core/deps.py::require_permission`,
  `services/permission_service.py`, and
  `services/approval_service.py::authorize_approval`.
- **HR_STAFF**, **APPROVER**, **EMPLOYEE** — granted granular permission
  codes (`models/enums.py::Permission`) via the `RolePermission` table.
  Default grants per role live in `Permission.DEFAULTS` and are applied
  by `seed.py`; HR_ADMIN can also edit them live via **Roles &
  Permissions** in the UI. Permission codes now span all 4 modules:
  `employee.*`, `attendance.*`/`roster.manage`, `leave.*`,
  `payroll.*`/`payslip.view`/`fnf.process`, `compliance.*` — grep
  `Permission` in `enums.py` for the full current list before adding a
  new one; each new module added its own set of codes following the
  existing `noun.verb` convention.
- Gate new endpoints with `core/deps.py::require_permission(code)`, not
  hand-rolled role checks.
- **Cost Center scoping**: `UserCostCenterScope` restricts which Cost
  Centers a non-HR_ADMIN user can see/act on
  (`services/permission_service.py::can_see_cost_center`,
  `user_cost_center_ids`). Reused by every module's list endpoints, not
  just Module 1.
- **Field-level access**: `permission_service.py::mask_sensitive_fields`
  strips Aadhaar/PAN/bank account number+IFSC/statutory numbers from
  `GET /employees/{id}` responses unless the caller has
  `employee.sensitive.view`.
- **SUPER_ADMIN** — a 5th role, added later, exclusively for the database
  backup/restore tools (`routers/admin.py`, `GET /admin/db-backup`,
  `POST /admin/db-restore`, gated by `core/deps.py::require_super_admin`
  — a strictly narrower gate than `require_hr_admin`, so **HR_ADMIN
  itself cannot reach these two routes**). Everywhere else, SUPER_ADMIN
  is a superset of HR_ADMIN — every `role.name == RoleName.HR_ADMIN`
  bypass check in the codebase (`require_permission`, `permission_service`,
  `approval_service.authorize_approval`, the bulk-import upsert branch,
  `_save_or_request`, etc.) checks `in (RoleName.HR_ADMIN,
  RoleName.SUPER_ADMIN)` instead of a single equality, so grep for that
  tuple (not a lone `== RoleName.HR_ADMIN`) if adding a new admin-bypass
  check. Frontend: `MainLayout.jsx`'s nav-visibility `roles`/`perm`
  checks and `UsersAdmin.jsx`'s `isSuperAdmin` gate mirror this. Seeded as
  `superadmin`/`SuperAdmin@123`. Mirrors sunlease-expms's identical
  SUPER_ADMIN role and db-backup/restore feature (same hot-swap
  mechanism: validate the upload on a throwaway temp-file copy via
  `PRAGMA integrity_check`, timestamp-backup the current file, `engine.dispose()`
  then atomically `shutil.move` the new file in, re-run `migrate()` —  no
  app restart needed).

## Approval routing + Change Requests (v2 — blueprint §15)

- **`ApprovalRule`** routes an approval to a role (or one specific user)
  by Cost Center + Employee Category + Transaction Type
  (`models/enums.py::TransactionType`), matched most-specific-first in
  `services/approval_service.py::find_approval_rule`. No matching rule →
  any `APPROVER` may act. New transaction types were added per module as
  needed (`ATTENDANCE_CORRECTION`, `OVERTIME_APPROVAL`, `LEAVE_APPLICATION`,
  `PAYROLL_PROCESSING`) — the last one is the one exception that calls
  `find_approval_rule` directly rather than through `authorize_approval`,
  since a payroll run is approved once per cost-center/month, not per
  episode (`payroll_service.approve_payroll_run`).
- **`ChangeRequest`** gates edits to an already-**ACTIVE** employee's
  identity/employment fields. `routers/employees.py::_save_or_request`:
  HR_ADMIN or non-ACTIVE episode → apply directly; otherwise → creates a
  `ChangeRequest`. `services/approval_service.py::apply_changes` is the
  single function used by both the direct path and
  `review_change_request`'s approve path.
  **This exact same branching is now also reused by the Employee bulk
  Excel upload** when a row's Employee Number matches an existing
  employee (`bulk_import_service.py::_apply_or_request`, mirrors
  `_save_or_request`) — a bulk-uploaded update to an ACTIVE employee
  queues a ChangeRequest instead of silently overwriting approved data,
  exactly like a human edit would. Bank/Statutory/OrgAssignment/
  CostAllocation/Address are NOT routed through ChangeRequest (already
  effective-dated append-only, or — for Address — a plain non-gated
  overwrite).
- Review queue: `GET /employees-change-requests`, `POST .../{id}/approve`,
  `POST .../{id}/reject`.

## Module 1 recap — Employee Data Management

Built: organization model, Employee + EmploymentEpisode, effective-dated
OrgAssignment + CostAllocation, 8-step Employee Creation Wizard, lifecycle
(Draft → Pending Approval → Active, plus Separation), granular RBAC +
Cost Center scoping + field-level masking + approval routing + a working
ChangeRequest workflow.

**Since the original build, the Employees list/profile UX was
substantially reworked:**
- Clicking an employee row **always** opens a read-only view
  (`EmployeeProfile.jsx`) — never the wizard directly, even for DRAFT
  rows. The "Overview" tab now renders `EmployeeReviewSummary.jsx`, a
  full single-page read-only summary (all wizard sections condensed onto
  one page) fed by the same `GET /employees/{id}` detail fetch — separate
  from and not a refactor of the wizard's own inline Review & Submit
  step, which is unchanged.
- Documents get a **preview popup** (`DocumentPreviewModal.jsx`) —
  `GET /employees/{id}/documents/{doc_id}/preview` streams the file with
  `media_type` set but **no `filename` kwarg on `FileResponse`** (that's
  what makes the existing `/download` endpoint force-download via
  `Content-Disposition: attachment` — mirrors how the employee photo
  endpoint already worked). The frontend fetches it as a blob (auth
  header required, can't just point an `<iframe src>` at the raw URL) and
  renders `<img>`/`<iframe>` from an object URL.
- List gets explicit **Edit** (→ wizard, all rows) and **Delete**
  (DRAFT rows only, hard delete) icon buttons, independent of row click.
- **Bulk Excel upload now upserts**: a row whose Employee Number matches
  an existing employee updates it (through the ChangeRequest-aware path
  above) instead of erroring "already in use". `import_workbook` returns
  `{created, updated, submitted_for_approval, errors}`.

Still deliberately deferred: Cloudflare R2 document upload (local disk
only for now, `boto3` sits unused in requirements.txt), employee
self-service login, Previous Employment model/UI, separation approval
routing (not yet routed through `ApprovalRule`).

## Module 2 — Attendance + Leave

**Attendance**: `ShiftMaster` (master shift definitions), `RosterEntry`
(one row per episode per date — shift assignment, weekly-off/rest-day/
holiday flags, double-shift via a second `shift_id`), `AttendanceRecord`
(actual marked attendance, status + late/early/overtime minutes),
`AttendanceException`, `AttendanceApprovalRequest` (correction/overtime,
routed through the standard approval engine). `WeeklyOffPattern` is a
recurring-rule *generator*, not the source of truth — a service call
materializes it into concrete `RosterEntry` rows for a date range, which
HR can then hand-edit per day without fighting the pattern.

**Leave**: `LeaveType`, `LeaveEligibilityRule` (specificity-cascade
matched like `find_approval_rule`), `LeaveBalance` (lazily accrued on
read — no scheduler in this codebase, MONTHLY/YEARLY accrual computed
on-demand), `LeaveApplication` (balance deducted on approval, not on
apply; blocked from applying on a pure weekly-off/holiday day; supports a
single file attachment per application, stored under
`HRMS_UPLOAD_DIR/leave-attachments/`), `HolidayCalendar`.

**App-level filter**: `GlobalFilterContext`/`GlobalFilterBar` (year,
month, cost_center_id — persisted to localStorage) sits above every page
and scopes Employees/Attendance/Leave list endpoints via a shared overlap
helper, `employee_service.episodes_in_cost_center_during(db,
cost_center_id, start_date, end_date)` — "who was active in cost center X
during month Y," reused across every module's monthly views (Attendance
Register, Attendance Grid, Payroll processing, Compliance aggregation).
Explicit per-page consumption (each page reads the context and passes
params into its own fetch), not an axios interceptor — most endpoints
don't want auto-scoping.

**Attendance Register** (`AttendanceRegister.jsx`) is two-mode via a
`?episode_id=` query param: a **summary** list (all employees active
that period, attendance counts per status + late/early/OT, driven
entirely by the global filter) and a **detail** drill-down for one
employee (mark/correct/exceptions). **Attendance Grid** is a separate
spreadsheet-style bulk entry/view page, plus bulk Excel
upload/download mirroring the Module 1 bulk-import pattern exactly
(template download, per-row `db.begin_nested()` savepoint, upsert via
the same `mark_attendance` used by manual entry so late/early/overtime
stay consistent either way).

## Module 3 — Payroll Management

**Salary structure is per-component, effective-dated** — not a
whole-template switch (deliberately diverging from `salary-app`'s
`EmployeeTemplateAssignment` design, to match this repo's existing
effective-dating convention instead): `SalaryComponent` is the master
(code, `component_type`, `default_calculation`), `SalaryStructureComponent`
is the per-employee dated assignment (amount/percentage/formula). A
`SalaryStructure.jsx` page lets you **Edit** or **End** (discontinue with
no replacement) any active row, and toggle a **"Show Full History"**
view of every version, past and present.

**Four `component_type` values**, not three:
- `EARNING` — added to Gross Earnings, prorated by attendance.
- `DEDUCTION` — subtracted from Gross Earnings for Net Pay, fixed
  monthly amount (not prorated) unless overridden.
- `EMPLOYER_CONTRIBUTION` — employer-side PF/ESI/LWF, rolls into
  `employer_cost_total` (CTC), never touches employee take-home.
- `ADDITION` — **added on top of Net Pay as `total_payable`, but
  deliberately excluded from Gross Earnings/Gross Deductions/Net Pay and
  therefore from the PF/ESI wage base**. This is how Bonus and monthly
  variable pay (performance/attendance-linked pay) are modeled — they're
  real money paid out, but shouldn't inflate the statutory wage
  calculation. Still prorated by attendance like earnings. `Payslip` has
  both `net_pay` (the formal Gross-minus-Deductions figure) and
  `additional_pay`/`total_payable` (`net_pay + additional_pay`, the real
  disbursed amount) as separate persisted fields — the payslip UI shows
  both, labeled, not blended into one number.

**`default_calculation`**: `FIXED`, `PERCENTAGE_OF_BASIC` (was silently
broken/ignored until fixed mid-project — now correctly resolves via the
formula engine as sugar for `BASIC * pct / 100`), or `FORMULA`.

**Formula engine** (`payroll_service.py`, `simpleeval`-based, adapted
from `salary-app`'s formula-engine idea but built fresh, not copied):
- A component's `formula` string can reference **other component codes**
  by name (multi-pass dependency resolution — `GROSS = BASIC + HRA +
  CONVEYANCE` works regardless of insertion order, circular/missing refs
  reported as errors rather than looping) and **attendance day-count
  variables**: `PRESENT`, `ABSENT`, `HALF_DAY`, `ON_LEAVE`, `WEEKLY_OFF`,
  `HOLIDAY`, `LATE_DAYS`, `EARLY_DEP_DAYS`, `OT_MIN`, `NOT_MARKED` — these
  exactly mirror `AttendanceRegister.jsx`'s summary columns
  (`compute_day_variables`), so a formula's numbers always match what HR
  sees in the register for the same period.
- Whitelisted functions: `min`, `max`, `round`, `abs`, `ceil`, `floor`,
  `roundup(value, nearest)`, `rounddown(value, nearest)` (case-insensitive
  aliases both ways), plus spreadsheet-style `IF(cond, then, else)`,
  `AND(...)`, `OR(...)` — **must be ALL CAPS**, since `if`/`and`/`or` are
  Python keywords and a lowercase call is never valid syntax to begin
  with. `IF` nests arbitrarily (it's just a function call).
- A `SalaryStructureComponent.formula` (per-employee) overrides the
  component's own default `formula` when both are set.
- **`SalaryComponentOverride`**: a one-month exception to a recurring
  component's computed value (e.g. Group Insurance is normally ₹50 but
  wasn't collected this month → override to 0 for just that
  episode+month) — used exactly as entered, no proration, no formula
  re-evaluation. Also the intended mechanism for feeding a
  monthly-variable `ADDITION` component (e.g. this month's actual
  performance bonus figure) its value each period.

**`SalaryTemplate`** — reusable structure blueprints scoped to a Cost
Center and/or Project, or global when both are null (matched
most-specific-first, same cascade idea as `find_approval_rule`/
`find_eligibility_rule`). "Load from Template" copies a template's
component rows into an employee's structure as an **editable** starting
point — every value can be changed before applying, nothing is locked in
verbatim. A "Sample Payslip" preview (both on templates and on an
employee's live structure) computes a hypothetical fully-worked 31-day
month via the same formula engine, excluding statutory deductions (which
need real per-employee eligibility, not a template abstraction).

**Payroll processing** (`process_payroll_run`): earned-days calculation
from Attendance + Leave, resolves every structure component (formula/
percentage/fixed, with overrides taking priority), computes PF/ESI/PT/LWF
from `StatutoryConfig`/`ProfessionalTaxSlab` (admin-editable data, not
hardcoded rates — seeded with the standard current PF 12%/₹15,000
ceiling and ESI 0.75%/3.25%/₹21,000 ceiling as a starting point), splits
cost via `CostAllocation` into `PayslipCostSplit`. Real
**DRAFT→PROCESSED→APPROVED→LOCKED** workflow — a locked/approved run
refuses reprocessing (the explicit gap this closes vs. `salary-app`,
which silently overwrites on re-run). **Full & Final Settlement**
computes leave encashment + gratuity (Payment of Gratuity Act formula,
≥5 years service + `StatutoryInfo.gratuity_eligible`) at separation —
gratuity is deliberately never a monthly deduction, it's an employer-
funded terminal benefit.

## Module 4 — Statutory Compliance

`ComplianceRecord` aggregates already-computed `PayslipLine` amounts by
scheme (PF/ESI/PT/LWF) per cost-center/month — it does **not** recompute
anything, payroll processing is the single source of truth for the
numbers. GRATUITY is a special case, aggregated from `FullFinalSettlement`
rows instead (no monthly PayslipLine exists for it). Re-aggregating a
period preserves an already-`FILED` record's status/reference number
rather than resetting it. Downloadable per-scheme statement exports are
explicitly documented (in both the endpoint docstring and the UI) as
best-effort, **not** government-portal-certified — same honesty
`salary-app` itself gives for its non-ESIC-certified templates.

## Outbound email

`backend/app/services/email_service.py` — two transports, auto-selected:
HTTP relay (`HRMS_MAIL_RELAY_URL`/`_SECRET`, for platforms that block
outbound SMTP — deploy `backend/scripts/cpanel-mail-relay.php` to the
mailbox's own cPanel server first) or direct SMTP
(`HRMS_SMTP_*`). Ported from the sibling `sunlease-expms` project's
identical relay design, with the attachment made optional (`send_email(...,
attachment_bytes=None)`) since most HRMS notifications won't have one.
**Infrastructure only as of this writing — nothing in the app calls
`send_email()` yet.** Env vars live in `.env`/`.env.example` and are
wired through `docker-compose.yml`'s `environment:` block (adding a var
to `.env` alone does **not** reach the container — compose only
auto-substitutes `.env` values into the compose file itself, each var
still needs its own line in `environment:`).

## Testing pattern used throughout this project

**Never `rm -f ../data/hrms.db` as a routine step.** After a model
change, just restart uvicorn — `app/migrate.py` runs automatically on
startup and additively applies the diff (new tables/columns) with zero
data loss. Only reset the database if the user explicitly asks for a
clean slate, or a change needs a rename/retype that `migrate.py` can't do
— and even then, ask first. The same discipline applies to the **live
Docker container's** `./data` volume — it's the shared dev database, not
disposable; any manual test data created via direct DB scripting during
verification gets cleaned up afterward, same as any other row.

Start uvicorn with:
```bash
nohup uvicorn app.main:app --host 127.0.0.1 --port 8010 > /tmp/hrms_uvicorn.log 2>&1 < /dev/null &
disown
```
in its own tool call (background processes die at tool-call boundaries in
this environment) — start it, then in the *next* tool call curl against
it. Drive tests with `curl` covering both the happy path and the
400/403/404 guardrails.

After every frontend change: `cd frontend && npm install -q && npm run
build` must succeed with zero errors before considering the change done.

Port 8000 is used by other local projects on this machine — this
project's backend runs on **8010** in dev, **8020** via Docker.

## Seed data

`backend/app/seed.py` (idempotent, safe to re-run) creates, across all 4
modules: all `RoleName` roles + default `RolePermission` grants, an
HR_ADMIN (`admin`/`Admin@123`), HR_STAFF (`hrstaff`/`HrStaff@123`) and
APPROVER (`approver`/`Approver@123`) user, sample org structure (Company/
Cost Center/Department/Project/Employee Categories), a global-fallback
`ApprovalRule`, 3 `ShiftMaster` rows, 3 `LeaveType` rows (CL/SL/EL) with
global `LeaveEligibilityRule`s, ~10 `SalaryComponent` rows (Basic/HRA/
Conveyance/Special Allowance + PF/ESI/PT/LWF + Employer PF/ESI), and one
active `StatutoryConfig` row at the seeded PF/ESI rates.
`ProfessionalTaxSlab` is deliberately left empty (state-specific — admin
fills in for their actual state rather than the seed guessing wrong
numbers).

All of the above only happens in the default `HRMS_SEED_MODE=full`. Set
`HRMS_SEED_MODE=minimal` for a real production seed — only the 5 Role
rows + their `Permission.DEFAULTS` grants + `admin`/`superadmin` get
created, nothing else; HR Admin builds the org structure, master data,
and any additional users through the app itself.

## What's left

Per the original blueprint, all 4 modules are now built at a working v1
level. Explicitly deferred items are called out per-module above; the
recurring theme across all of them is: no live government-portal
integration (compliance filing is downloadable statements only), no
scheduled/cron-based background jobs anywhere in this codebase (leave
accrual and everything else that might want one is computed lazily on
read instead), and Cloudflare R2 / employee self-service login are still
open from Module 1's original deferred list.
