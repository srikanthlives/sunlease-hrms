# HRMS — Employee Data Management (Module 1)

Module 1 of a 4-module HRMS (Employee Data Management, Attendance, Payroll,
Compliance), built from the attached blueprint
(`HRMS_Module_1_Employee_Data_Management_Blueprint.docx`). Employee Data
Management is the system-of-record foundation the other modules will later
read from.

## Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.x, Pydantic v2, JWT auth
- **Database:** SQLite (file-based, zero setup)
- **Frontend:** React 18 + Vite + React Router 6 + Axios, Tailwind CSS 3.4

## What's implemented

**Phase 1 — core:**
- Organization model: Company → Cost Center → Project / Department, plus
  admin-configurable Employee Categories
- Employee (person) vs Employment Episode (a stint of employment) —
  rejoining creates a new episode, not a duplicate person record
- Effective-dated Organizational Assignment and Cost Allocation, enforcing
  "one active Department per employee at a time"
- 8-step Employee Creation Wizard, saveable as Draft at any point: Personal,
  Employment, Organizational Assignment, Statutory, Bank, Documents (stub),
  Dependents/Nominees, Review & Submit
- Employee lifecycle: Draft → Pending Approval → Approved/Active, plus
  Separation
- Employee Profile / 360° view (Overview, Personal, Employment,
  Organization, Statutory, Bank, Dependents, Nominees, Audit History)
- Append-only audit log on every create/update/status-change

**Version 2 — RBAC + approval routing:**
- Granular permissions (`employee.view/create/edit/approve/separate`,
  `employee.sensitive.view/edit`, `change_requests.review`, etc.), edited
  live per role from the Roles & Permissions admin page
- Cost Center data scoping — non-HR_ADMIN users only see/act on employees
  in their assigned Cost Centers
- Field-level access: Aadhaar/PAN/bank details/statutory numbers are
  hidden from anyone without `employee.sensitive.view`
- Multi-level approval routing (Cost Center + Employee Category +
  Transaction Type → Approver Role/User, with a global fallback) for new
  employee approval
- A real Change Request workflow — edits to an already-Active employee's
  identity/employment fields require Approver review instead of applying
  directly
- Admin UI: Users & Roles, Roles & Permissions, Approval Rules, Change
  Requests

**Deferred to a later pass** (see `CLAUDE.md` for the full list): Cloudflare
R2 document upload, the multi-level approval routing engine, field-level
RBAC, and the employee self-service portal.

## Running it

The fastest way to run everything (backend + frontend build) is:

```bash
./startup.sh
```

It creates the backend venv, installs dependencies, builds the frontend,
and starts uvicorn on port 8000. For Docker or Railway, see
[DEPLOYMENT.md](./DEPLOYMENT.md).

To run backend and frontend separately in dev mode instead (this repo's
own dev sessions use port 8010 for the backend to avoid clashing with
other local services on 8000 — adjust `frontend/.env.development` if you
change it):

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m app.seed          # creates ../data/hrms.db, roles, and a sample org structure
uvicorn app.main:app --reload --port 8010
```

The API is now at `http://localhost:8010`, with interactive docs at
`http://localhost:8010/docs`.

Seeded logins:

| Role | Username | Password |
|---|---|---|
| HR Admin | `admin` | `Admin@123` |
| HR Staff | `hrstaff` | `HrStaff@123` |
| Approver | `approver` | `Approver@123` |

HR Admin bypasses all permission/scope checks. HR Staff and Approver are
both scoped to the seeded Cost Center (`CC-PDY`) so the RBAC and
approval-routing flow is testable right away.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173` and talks to the API at the URL in
`.env.development` (`VITE_API_URL`, defaults to `http://localhost:8010`).

## Project layout

```
backend/
  app/
    core/        settings, JWT + password hashing, role-check dependencies
    db/          SQLAlchemy session/engine
    models/      SQLAlchemy models (models.py) + string-constant enums.py
    schemas/     Pydantic request/response models
    services/    business logic — audit, org-assignment/allocation rules
    routers/     FastAPI route handlers
    seed.py      idempotent seed script
    migrate.py   auto-migration script (see below)
    main.py      app entrypoint
frontend/
  src/
    api/         axios client with auth interceptor
    context/     auth context (JWT storage, current user)
    layouts/     sidebar shell
    pages/       Login, Employees, EmployeeWizard, EmployeeProfile,
                 Organization, AuditLogs
    components/  shared UI primitives (ui.jsx)
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
