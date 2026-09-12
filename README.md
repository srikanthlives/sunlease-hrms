# HRMS — Sunlease Renewables

A full 4-module HRMS built from the original blueprint
(`HRMS_Module_1_Employee_Data_Management_Blueprint.docx`): **Employee Data
Management**, **Attendance + Leave**, **Payroll Management**, and
**Statutory Compliance**. Employee Data Management is the system-of-record
foundation the other three modules read from.

## Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.x, Pydantic v2, JWT auth
- **Database:** SQLite (file-based, zero setup)
- **Frontend:** React 18 + Vite + React Router 6 + Axios, Tailwind CSS 3.4
- **Formula engine:** `simpleeval` (sandboxed expression evaluation for
  payroll salary-component formulas)

## What's implemented

**Module 1 — Employee Data Management:**
- Organization model: Company → Cost Center → Project / Department, plus
  admin-configurable Employee Categories/Designations/Work Locations/
  Employment Types (hard-deletable if unused, deactivated otherwise)
- Employee (person) vs Employment Episode (a stint of employment) —
  rejoining creates a new episode, not a duplicate person record
- Effective-dated Organizational Assignment and Cost Allocation
- 8-step Employee Creation Wizard (Draft-saveable at any point)
- Lifecycle: Draft → Pending Approval → Active, plus Separation; a Draft
  can be deleted outright
- Read-only Employee Review summary (all sections on one page), document
  preview popups, list-level Edit/Delete actions
- Bulk Excel upload that both creates new employees and **updates**
  existing ones (routed through the same approval rules as a manual edit)
- Granular RBAC, Cost Center data scoping, field-level sensitive-data
  masking, multi-level approval routing, a real Change Request workflow
- Append-only audit log

**Module 2 — Attendance + Leave:**
- Shifts, rosters (with duty allocation, weekly-off/rest-day flags, double
  shifts), attendance capture with automatic late/early/overtime
  calculation, exceptions, correction/overtime approval requests
- Leave types, eligibility rules, lazily-accrued balances, applications
  (with a supporting-document attachment), approvals, holiday calendar
- An app-level Month + Cost Center filter that scopes every module's list
  views consistently
- Attendance Register (summary + per-employee drill-down) and a
  spreadsheet-style Attendance Grid, both with bulk Excel upload

**Module 3 — Payroll Management:**
- Salary components (Earning / Deduction / Employer Contribution /
  Addition) and per-employee, effective-dated salary structure
- A formula engine for component values — reference other components by
  code or attendance day-count variables, with `IF`/`AND`/`OR`/`MIN`/
  `MAX`/`ROUND`/`ROUNDUP`/`ROUNDDOWN` etc.
- One-month value overrides (e.g. a component normally deducted but
  waived this month) and an `Addition` component type for bonuses/
  monthly variable pay that's paid out without inflating Gross/Net or the
  PF/ESI wage base
- Salary Templates (scoped to a Cost Center/Project or global) that load
  into an employee's structure as an editable starting point, plus a
  Sample Payslip preview
- Monthly payroll processing with a real Draft → Processed → Approved →
  Locked workflow, cost-center/project cost-allocation splitting, and
  Full & Final Settlement (leave encashment + gratuity) at separation

**Module 4 — Statutory Compliance:**
- PF / ESI / Professional Tax / LWF / Gratuity aggregated from processed
  payroll data per cost-center/month, with a filed/paid status and
  challan reference tracking, plus downloadable (best-effort, not
  government-portal-certified) statement exports

**Cross-cutting:**
- Outbound email infrastructure (direct SMTP or an HTTP mail relay for
  hosts that block outbound SMTP) — wired up, not yet called by any
  feature

See `CLAUDE.md` for the full architectural detail and what's still
deliberately deferred in each module.

## Running it

### Docker (recommended — matches the deployed local instance)

```bash
docker compose up -d --build
```

Serves on **http://localhost:8020**, backed by a persistent `./data`
volume (SQLite DB + uploaded attachments/documents). Set
`HRMS_SECRET_KEY` in a `.env` file first (see `.env.example`) — outbound
email settings are optional and can be left blank.

### Manual dev setup

The fastest way to run everything (backend + frontend build) locally
without Docker is:

```bash
./startup.sh
```

It creates the backend venv, installs dependencies, builds the frontend,
and starts uvicorn on port 8000. For Docker or Railway specifics, see
[DEPLOYMENT.md](./DEPLOYMENT.md).

To run backend and frontend separately in dev mode instead (this repo's
own dev sessions use port 8010 for the backend to avoid clashing with
other local services on 8000 — adjust `frontend/.env.development` if you
change it):

#### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m app.seed          # creates ../data/hrms.db, roles, and a sample org structure
uvicorn app.main:app --reload --port 8010
```

For a **production** deployment, seed with `HRMS_SEED_MODE=minimal` instead —
this creates only the 5 role definitions (HR_STAFF/APPROVER/EMPLOYEE stay
assignable to real users later) plus the two admin logins below, with **no**
sample org structure, master data, or hrstaff/approver test users. HR Admin
creates everything else through the app itself:

```bash
HRMS_SEED_MODE=minimal python -m app.seed
```

The API is now at `http://localhost:8010`, with interactive docs at
`http://localhost:8010/docs`.

Seeded logins:

| Role | Username | Password |
|---|---|---|
| HR Admin | `admin` | `Admin@123` |
| HR Staff | `hrstaff` | `HrStaff@123` |
| Approver | `approver` | `Approver@123` |
| Super Admin | `superadmin` | `SuperAdmin@123` |

Super Admin is a superset of HR Admin everywhere HR Admin is allowed,
plus exclusive access to Database Backup & Restore (Users & Roles page)
— downloading/replacing the live SQLite database, which even HR Admin
itself cannot do.

HR Admin bypasses all permission/scope checks. HR Staff and Approver are
both scoped to the seeded Cost Center so the RBAC and approval-routing
flow is testable right away.

#### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173` and talks to the API at the URL in
`.env.development` (`VITE_API_URL`, defaults to `http://localhost:8010`).

## Outbound email (optional)

`backend/app/services/email_service.py` supports two transports, picked
automatically based on which environment variables are set — see
`.env.example` for the full list (`HRMS_SMTP_*` for direct SMTP, or
`HRMS_MAIL_RELAY_URL`/`HRMS_MAIL_RELAY_SECRET` for the HTTP relay,
`backend/scripts/cpanel-mail-relay.php`, needed on platforms that block
outbound SMTP). Leaving all of these blank is fine — nothing in the app
currently requires email to function; it's infrastructure for future
notification features.

## Project layout

```
backend/
  app/
    core/        settings, JWT + password hashing, role-check dependencies
    db/          SQLAlchemy session/engine
    models/      SQLAlchemy models (models.py) + string-constant enums.py
    schemas/     Pydantic request/response models, one file per module
    services/    business logic — audit, approval routing, per-module
                 processing (employee, attendance, leave, payroll,
                 compliance), bulk-import, email
    routers/     FastAPI route handlers, one file per module
    scripts/     cpanel-mail-relay.php (deploy to your mail server)
    seed.py      idempotent seed script
    migrate.py   auto-migration script (see below)
    main.py      app entrypoint
frontend/
  src/
    api/         axios client with auth interceptor
    context/     auth context + the app-level GlobalFilterContext
                 (month/year/cost-center, used across every module)
    layouts/     sidebar shell + GlobalFilterBar
    pages/       one or more pages per module (Employees, Attendance,
                 Leave, Payroll, Compliance, Organization Setup, Audit)
    components/  shared UI primitives (ui.jsx) + a few cross-page
                 components (EmployeeReviewSummary, DocumentPreviewModal)
```

## Schema changes / database migrations

There's no Alembic wired in — `backend/app/migrate.py` diffs the live
SQLite database against the current models on every app startup and
**additively** applies the difference (new tables, new columns). It never
drops, renames, or retypes anything.

```bash
cd backend
python -m app.migrate   # explicit run with a readable summary
```

For a genuine drop/rename/retype, or to start clean:

```bash
rm -f data/hrms.db && cd backend && python -m app.seed
```

Only do this if you explicitly want a clean slate — the running Docker
container's `./data` volume is real, persisted data, not disposable.
