# Sunlease — Salary & Payroll Management App

A full-stack payroll application:
- **Backend:** Python, FastAPI, SQLAlchemy ORM, SQLite
- **Frontend:** React (Vite), Tailwind CSS, shadcn-style UI components
- **Auth:** JWT, with three roles — Admin, Payroll Processor, Employee

## What it does

1. **Salary Templates** — Admin designs a template (given a template number, e.g. `T-001`)
   made up of **components**. Each component can be:
   - **Fixed** — a flat value (e.g. Basic Pay = 30,000)
   - **% of another component** — e.g. HRA = 40% of BASIC
   - **Formula** — a safe expression referencing other component codes and attendance
     variables (e.g. `BASIC + HRA + CONV`)
   - **Variable** — value is *not* fixed by the template; it defaults to a `default_value`
     (e.g. Performance Bonus defaults to 2000) but can be **overridden per employee, per month**
     via a manual entry or an Excel bulk upload. The uploaded value overrides the default
     for that employee for that month only — exactly like the "2000 → 1500" example.
   - Any component can also be marked **prorate by attendance**, so it scales with
     `present_days / total_days` for that month.

2. **Employees** — Admin creates employee records (one at a time, or **bulk-uploaded via
   Excel**) and assigns a default template. Templates can also be **attached with an effective
   date** so an employee's structure can change over time — see "Dated template assignments" below.

3. **Attendance** — a full day-by-day system: mark each employee's status per day (Present,
   double-duty, half day, absent, earned leave, week off) on an interactive monthly grid, bulk
   upload for a single day or a whole month, and track earned-leave accrual — all driving payroll
   proration automatically. See "Attendance Management System" below for details.

4. **Monthly Variable Upload** — Excel upload (or manual single entry) of overrides for any
   component flagged "variable" on an employee's template, for a specific month.

5. **Ad-hoc Entries** — one-off manual earnings/deductions for a specific employee & month,
   e.g. a **uniform deduction** applied only in an employee's resignation month.

6. **Cost to Company (CTC) / Employer Contributions** — a component can also be an
   **Employer Contribution** (e.g. Employer PF, Employer ESI) — this is resolved and totalled
   into a `ctc_total` figure, but it **never appears on the employee's payslip** and never
   affects gross earnings, gross deductions, or net pay. Admin/payroll users get a **"View CTC"**
   link next to every payslip showing the full cost breakdown (employee earnings + employer
   contributions = CTC); the CTC total is also shown as its own column in the admin/payroll
   payslip summary tables (`/payslips`, `/run-payroll`). Employees only ever see their own
   take-home payslip — the API itself strips employer-cost data from employee-facing responses,
   it isn't just hidden in the UI.

7. **Reference / notional components** — a component type that's never paid and never shown
   anywhere (not on the payslip, not in the CTC view's totals), but whose resolved value can be
   used by *other* formulas. Example: `GROSS_SALARY = BASIC + DA + HRA` as a Reference component,
   then an ESIC deduction formula can check `GROSS_SALARY <= 21000` to decide eligibility.

8. **Run Payroll** — computes payslips for a month (all active employees or a selection):
   resolves every template component in dependency order (handling formulas automatically,
   regardless of table order), applies attendance proration, applies that month's variable
   overrides, adds any ad-hoc entries, and stores the resulting payslip + line items **in the
   template's defined order** (components can be reordered with the ↑/↓ arrows in the template
   builder, and that order is what shows up on the payslip).

9. **Payslips** — view a computed payslip with a full earnings/deductions breakdown,
   gross earnings, gross deductions and net pay. Employees can only see their own.

10. **Salary Payments & balances** — salaries can be paid in multiple part-payments with their
    own transaction IDs; every payslip shows the payments received and any remaining balance.

11. **Bank Payments** — generates IDFC FIRST Bank's bulk NEFT payment file (split into a Coach Captain file
    and a Staff file) with each employee's outstanding balance as the amount, ready to upload.

12. **Compliances** — PF (UAN), ESI, and Mediclaim identifiers per employee with portal links,
    plus downloadable PF/ESI/Mediclaim statements built from that month's actual payroll data.

## Roles

| Role | Can do |
|---|---|
| **admin** | Everything: manage users, employees, salary templates, attendance, uploads, ad-hoc entries, run payroll, view all payslips |
| **payroll_processor** | Manage employees (read/update), attendance, monthly variable uploads, ad-hoc entries, run payroll, view all payslips — cannot create/edit salary templates or manage users |
| **employee** | View only their own employee record and their own payslips |

Role checks are enforced **server-side** in FastAPI dependencies (`app/deps.py`), not just hidden in the UI.

---

## Attendance Management System

`/attendance`, `/attendance/upload`, and `/attendance/el-balances` form a full day-by-day system
— three separate pages grouped under a collapsible **Attendance** section in the sidebar, all
scoped to the global period selector and only showing employees **eligible for that period**
(same joined-by/left-before rule payroll uses):

### Monthly Grid (`/attendance`)
Every eligible employee × every calendar day of the month, in one scrollable table. Click any
day's cell to mark or change that day's status inline — it saves immediately. Each row ends with
summary columns — **Total, Present, WO, Rest (R), Absent, EL, LOP** — and the table footer shows
the same totals summed across every employee shown.

**Status codes:**
| Code | Meaning |
|---|---|
| `P` | Present |
| `2P` | Double duty (e.g. a driver who did two shifts) |
| `HD` | Half day |
| `AB` | Absent (unpaid) |
| `EL` | Earned leave (paid, drawn from the EL balance) |
| `WO` | Week off (paid, doesn't consume EL) |
| `R` | Rest day (unpaid compensatory rest, e.g. for drivers — not worked, not paid, doesn't consume EL) |

**Summary formulas:**
```
TOTAL   = P + 2P×2 + WO + EL      (+ 0.5×HD)
PRESENT = P + 2P×2                (+ 0.5×HD)
WO      = count of WO days
R       = count of R days
AB      = count of AB days
EL      = count of EL days
LOP     = max(0, AB − EL)
```
`TOTAL` feeds `PRESENT_DAYS` in payroll formulas (attendance proration), and `LOP` feeds
`LOP_DAYS` — both available as formula variables, same as before. A double-duty employee's total
can exceed the calendar days in the month (e.g. 32 paid days in a 30-day month), which correctly
gives them a proration ratio above 100%. Rest days (`R`) are excluded from `TOTAL`/`PRESENT`
entirely — they're neither worked nor paid.

**Earned leave enforcement:** marking a day `EL` is rejected with a clear error — on the grid, in
a single-day upload, and in a whole-month upload — if the employee doesn't have enough EL balance
accrued as of that month. Nothing else in a bulk upload is affected; only the offending row is
skipped and reported.

### Bulk Upload (`/attendance/upload`)
Two upload modes:
- **Single day** — columns `employee_code, status, remarks` (optional); the date is picked once
  for the whole file.
- **Whole month** — WIDE format, one row per employee: columns `employee_code, employee_name`
  (name is optional/informational only — matching is always by code), then one column per day of
  the month — `1, 2, 3 … 28/30/31` — each holding that day's status code. Blank day cells are
  left unmarked. Rows are processed day-by-day in date order (column order), so earned-leave
  balance checks see earlier days in the same file first.

Sample files for both (including an `R` example) are in `sample_data/`.

### Earned Leave Balances (`/attendance/el-balances`)
Shows, for the selected year up to the selected month: days actually worked (`P`/`2P`/`HD` only —
`EL`, `WO`, and `R` don't count as "worked"), EL accrued, EL taken, and the resulting balance.

**Accrual rule: 1 EL for every 20 days worked, capped at 15 per calendar year.** Verified against
the exact boundary cases (19 days → 0, 20 → 1, 39 → 1, 40 → 2, capped at 15 no matter how many
days are worked beyond that).

### Backward compatibility
The previous month-level summary entry (`total_days`/`present_days`/etc., no daily breakdown)
still exists as a fallback at the API level (`GET/POST /attendance`, `POST /attendance/upload`) —
if an employee/month has no daily records at all, payroll falls back to that row, and only
assumes full attendance if neither exists. It's no longer exposed in the UI in favor of the new
day-by-day grid, but nothing about existing data breaks.

## Payroll eligibility (date-driven, not status-driven)

An employee is included in a given month's payroll **based on their joining/leaving dates**,
not the `status` field:

- They must have **joined on or before** that month (`date_of_joining`).
- They must **not have left before** that month (`date_of_leaving` is empty, or falls on/after
  that month).

So if someone's last working day is in April, they're still included in **April's** payroll and
automatically excluded from **May's** onward — even if nobody ever changed their status away from
"active". The `/run-payroll` page's employee picker (`GET /employees/eligible?month=&year=`) only
ever lists employees eligible for the selected period, for exactly this reason.

**Stale payslip cleanup:** every payroll run first checks all existing payslips for the selected
month/year and deletes any that belong to an employee who is no longer eligible for that period
(e.g. a payslip was generated before their leaving date was entered). This happens automatically -
just re-run payroll for that month after correcting the leaving date, and the stale record is
removed and reported in the run's result.

## App-level period selector

Attendance, Monthly Variables, Ad-hoc Entries, Run Payroll, and Payslips all share a single
month/year selector, shown in the top bar (persisted in `localStorage`, so it's remembered across
reloads). Change it once and every one of those pages reflects the new period until you change it
again - no need to re-select the month on each page separately.

## App-level employee filters (sort, department, location)

A second bar sits right under the period selector — **"Employee filters"** — with Sort (by
employee name/code) and Department/Location dropdowns. It's genuinely app-level: the same
`EmployeeFilterContext` (persisted to `localStorage`, same pattern as the period selector) drives
filtering/sorting on every page that lists employees, not just one:

- **Employees** (`/employees`) — the main employee table
- **Run Payroll** (`/run-payroll`) — the eligible-employees picker (a "Select all shown" button
  appears when a filter is active, so you can quickly scope a run to exactly what's filtered —
  note that running with *nothing* checked still targets every eligible employee, not just the
  filtered ones, unless you explicitly select them)
- **Attendance → Monthly Grid** (`/attendance`) — which employee rows appear in the grid
- **Attendance → Earned Leave Balances** (`/attendance/el-balances`) — which employees' balances are shown
- **Monthly Variables** (`/variable-upload`) — the employee picker and the active-overrides table
- **Ad-hoc Entries** (`/adhoc`) — the employee picker and the entries table
- **Salary Payments** (`/salary-payments`) — both the payments table and the employee picker
- **Compliances** (`/compliance`) — the employee compliance table
- **All Payslips** (`/payslips`) — the payslip table, plus its totals row (which sums only what's
  currently displayed)

Employees have a `location` field (alongside department/designation) for exactly this; set it on
the employee form, via bulk upload (`location` column), or when editing an employee. Change the
filters once from the top bar and every one of those pages reflects it immediately — a "Reset"
button appears next to the dropdowns whenever any filter is active.

## Location-based salary templates

Salary templates can optionally have a **location**. When attaching a template to an employee
(their default template, or a dated assignment), only compatible templates are offered:
- If the employee **has a location**, only templates with that **exact same location** are shown.
- If the employee **has no location set**, only **location-less** (general) templates are shown.

This keeps region-specific pay structures (e.g. different HRA rates or allowances per city) from
being accidentally attached to the wrong office.

**Cloning a template** — the "Clone" button on a selected template copies all of its components
into a brand-new template under a new template number/name (handy for spinning up a
location-specific variant, or a starting point for a new role, without rebuilding every
component by hand). The clone's location defaults to the source's, but you can change or clear it
before creating it.

## Bulk-replacing a template's components (with validation)

From the template builder, you can upload an Excel file to bulk-replace a template's components
instead of adding them one by one. Columns: `code, name, component_type, calculation_type, value,
formula, is_variable, default_value, prorate_by_attendance, sequence`.

Every row is validated **before** anything is applied — unknown component/calculation types,
non-numeric values, duplicate codes, missing formulas where required, and formula syntax errors
are all caught and reported with their row number. If there's any problem, **nothing is changed**
and you get the full list of errors to fix and re-upload; the replace only happens once every row
passes.

## Compliances (PF, ESI, Mediclaim)

The **Compliances** page lists each employee's PF (UAN), ESI (IP number), and Mediclaim policy
number, with the PF/ESI numbers linking out to the EPFO and ESIC portals. From the same page you
can download three filing-support statements for the selected period:

- **ESI statement** — fills the **actual ESIC "Monthly Contribution" upload template**
  (`app/resources/esi_template.xlsx`, as provided by ESIC — same headers, same instructions/reason-code
  reference sheet, same column order: IP Number, IP Name, No. of days wages paid/payable, Total
  Monthly Wages, Reason Code, Last Working Day). Only the data rows are replaced — download it and
  upload straight to the ESIC portal. Reason Code defaults to `0`; if an employee's last working
  day falls within the selected month, it's set to `2` ("Left Service") with the date filled in.
  Employees without an ESI number on file are skipped and listed in a response warning.
- **PF statement** — UAN, gross wages, employee & employer EPF contribution (pulled from that
  month's actual payslip lines), NCP days. No official EPFO template was provided for this one, so
  it's a practical starting-point statement — verify column requirements against the current EPFO
  ECR specification before filing.
- **Mediclaim statement** — policy number, department/designation, joining/leaving dates, and
  whether the row is an addition or a deletion (based on whether they've left). Also a
  starting-point statement, since insurers' formats vary.

PF/ESI contribution amounts (used in the PF statement and elsewhere) are read from payslip lines
with codes `PF`/`EMPLOYER_PF` and `ESIC`/`EMPLOYER_ESIC`; if a template uses different codes for
these, those columns come back blank for that employee.

## Bank bulk payment file (IDFC FIRST Bank)

From **Bank Payments**, enter the debit account number and transaction date and generate a ZIP
containing IDFC FIRST Bank's bulk NEFT upload format. This fills the **actual bank template**
(`app/resources/bank_payment_template.xlsx`, as provided by the bank) — the header row, the
instructions row, and every column are preserved exactly; only the data rows are replaced — split
into two files exactly as used at this organization:
- Employees with designation **"Coach Captain"** → `BLKPAYCC<MM><YYYY>.xlsx`
- Everyone else → `BLKPAYST<MM><YYYY>.xlsx`

Columns: Beneficiary Name, Account Number, IFSC, Transaction Type (NEFT), Debit Account Number,
Transaction Date, Amount, Currency (INR), Beneficiary Email, Remarks, and five Custom Header
columns — Custom Header 1 carries the employee code, Custom Header 2 the designation, as
requested. The **Amount** is each employee's outstanding **balance** for the period (net pay minus
anything already recorded under Salary Payments), so re-running this after a partial payment only
asks the bank for what's still owed. Employees missing a bank account are excluded with a warning;
missing IFSC is flagged but the row is still included.

## Salary payments & balances

Salaries don't have to be paid in one shot. From **Salary Payments**, record (individually or via
Excel upload — columns: `employee_code, amount, transaction_id, payment_date, remarks`) each
part-payment made towards a month's salary. Every payslip then shows:
- Every payment received that month, with its transaction ID and date
- **Total paid** so far
- The **balance** still owed (or "fully paid" / an overpaid notice if it's covered)

This is visible to the employee on their own payslip too (unlike CTC/employer-cost data), since
it's exactly the information they'd want to know about their own pay status.

## Sidebar organization

Monthly Variables, Ad-hoc Entries, Run Payroll, Salary Payments, Bank Payments, and All Payslips
are grouped under a collapsible **Payroll** section in the sidebar (click the group header to
expand/collapse). Dashboard, Employees, Salary Templates, Attendance, and the new **Compliances**
page remain top-level.

## Dated template assignments (a template can change over time)

An employee's salary template isn't fixed forever — from the **History** icon (🕐) next to
each employee in `/employees`, you can attach a template **effective from a given month/year**.
The most recent assignment that has started by the payroll period being run wins:

```
Jan 2026  →  Template A
Mar 2026  →  Template B
Mar 2027  →  Template C
```

- Payroll for **Jan–Feb 2026** uses **A**
- Payroll for **Mar 2026 – Feb 2027** uses **B**
- Payroll for **Mar 2027 onward** uses **C**

If no dated assignment applies yet for a given period (e.g. a payroll run for a month before
the earliest assignment, or an employee with no assignments at all), the employee's **default
template** (set on their record, or via bulk upload's `template_no` column) is used instead.
Every payslip records which template number was actually used (`template_no`), shown on both
the payslip and CTC breakdown pages, so past payslips stay traceable even after the template
changes again later.

## Managing employees, templates & overrides

- **Employee code and email** can both be edited after creation (`/employees`, edit dialog).
  Email is **optional** — leave it blank if the employee doesn't have one yet.
- **Deleting an employee** removes their attendance records, monthly variable overrides,
  ad-hoc entries, payslips (and payslip line items), and any linked login account —
  so the delete always succeeds cleanly rather than failing on a foreign-key error.
- **Deleting a salary template** is blocked with a clear error if any employee is still
  assigned to it; reassign those employees first, then delete.
- **Monthly variable overrides** can be deleted individually from the `/variable-upload` page
  (the template's default value applies again once removed) and are chosen from a **dropdown
  of that employee's variable components** (populated from their assigned template) rather
  than typed free-hand, so you can't accidentally target a component that isn't variable.

## Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Creates the SQLite DB, an admin user, a payroll-processor user,
# a sample template (T-001), and a sample employee (EMP001) with an employee login.
python seed.py

uvicorn app.main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`. Interactive API docs: `http://localhost:8000/docs`.

**Seeded logins:**
| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | admin |
| `payroll` | `payroll123` | payroll_processor |
| `asha.rao` | `employee123` | employee |

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` and proxies `/api/*` to the backend at
`http://localhost:8000` (see `vite.config.js`). Log in with any of the seeded users above.

---

## Excel upload formats

**Employee upload** (`/employees` page — required columns marked *):
| employee_code* | first_name* | last_name | email | phone | department | designation | location | date_of_joining | template_no | bank_name | bank_account | ifsc | pan | uan |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EMP002 | Rahul | Mehta | rahul.mehta@example.com | 9876543210 | Sales | Sales Executive | Mumbai | 2024-04-01 | T-001 | ICICI Bank | 987654321012 | ICIC0001234 | BCDEF2345G | 100200300401 |

Existing employees are matched (and updated) by `employee_code`; new codes are created.
`template_no` sets that employee's **default** template (not a dated assignment) if it matches
an existing template. Email is optional and left blank if not provided or already taken.

**Monthly variable component upload** (`/variable-upload` page):
| employee_code | component_code | value | remarks (optional) |
|---|---|---|---|
| EMP001 | PERF_BONUS | 1500 | Reduced after review |
| EMP001 | UNIFORM_DEDUCTION | 1200 | Resignation — uniform not returned |

**Attendance upload** (`/attendance` page):
| employee_code | total_days | present_days | paid_leave_days | lop_days | remarks |
|---|---|---|---|---|---|
| EMP001 | 30 | 28 | 1 | 1 | |

Sample files are in `sample_data/`.

> A component must be marked **"Variable"** on the template before it can be overridden
> via the variable upload — this is how the app knows Performance Bonus is manually
> adjustable, while Basic Pay is not.

## Formula reference variables

When writing a **Formula** component, you can reference:
- Any earlier-defined component's `code` (e.g. `BASIC`, `HRA`) — including Reference and
  Employer Contribution components, e.g. `GROSS_SALARY`
- `TOTAL_DAYS`, `PRESENT_DAYS`, `LOP_DAYS`, `PAID_LEAVE_DAYS`, `ATTENDANCE_RATIO`
- Functions: `min()`, `max()`, `round()`, `abs()`, `roundup(value, nearest=1)`, `rounddown(value, nearest=1)`, `ceil()`, `floor()`
- Comparisons and a ternary: `a if condition else b`

Example: `BASIC + HRA + CONV` or `(BASIC * 0.05) + PERF_BONUS`.
Components are resolved in multiple passes, so order in the table doesn't strictly matter for
*calculation* — but avoid circular references (A depends on B which depends on A). The order
components are listed in the template builder **is** the order they're shown on the payslip;
use the ↑/↓ arrows on each row to rearrange them.

**PERCENTAGE components** can use a full expression as their base, not just a single code —
e.g. HRA = 40% of `BASIC + DA` (write `BASIC + DA` in the base field), same functions available.

### Worked example: PF with a wage ceiling

A common real-world rule: **PF = 12% of (BASIC + DA)**, but if BASIC+DA exceeds ₹15,000,
PF is capped at 12% of ₹15,000 instead of the full amount. Set this up as:

1. Make sure `BASIC` and `DA` exist as components on the template (mark them
   `prorate_by_attendance` if they should scale with attendance — the formula will then
   automatically use their *already-prorated* values).
2. Add a component `PF`, type **Deduction**, calculation type **Formula**, with:
   ```
   min(BASIC + DA, 15000) * 0.12
   ```
   (equivalently, a ternary works too: `(BASIC + DA) * 0.12 if (BASIC + DA) < 15000 else 15000 * 0.12`)

That's it — the engine resolves `BASIC` and `DA` first, then evaluates the `PF` formula against
their resolved values, so the cap is applied correctly every month regardless of attendance.

### Worked example: ESIC using a Reference component + Employer Contribution

ESIC eligibility depends on gross salary, and both employee and employer pay their own share.
This is a great use for a **Reference** component plus **Employer Contribution** components:

1. Add `GROSS_SALARY` as a **Reference** component (never shown anywhere), formula:
   ```
   BASIC + DA + HRA + CONV + PERF_BONUS
   ```
2. Add `ESIC` as a **Deduction** (employee share), formula:
   ```
   roundup(GROSS_SALARY * 0.0075, 1) if GROSS_SALARY <= 21000 else 0
   ```
3. Add `EMPLOYER_ESIC` as an **Employer Contribution** (employer share — cost only, hidden from
   the payslip, visible only in the CTC view), formula:
   ```
   roundup(GROSS_SALARY * 0.0325, 1) if GROSS_SALARY <= 21000 else 0
   ```

The seeded demo template (`T-001`, created by `seed.py`) includes this exact setup — open it in
`/templates` after logging in as `admin` to see it working end to end.

## Project structure

```
backend/
  app/
    main.py            FastAPI app + router registration
    database.py         SQLAlchemy engine/session (SQLite)
    models.py           ORM models
    schemas.py           Pydantic request/response schemas
    security.py          password hashing + JWT
    deps.py               auth & role-based access dependencies
    formula_engine.py     core payroll computation engine
    utils/excel.py         Excel parsing for uploads
    routers/                one router per resource
  seed.py                bootstrap script
  requirements.txt
frontend/
  src/
    pages/                one file per screen
    components/ui/         shadcn-style primitives (Button, Card, Table, Dialog, ...)
    auth/AuthContext.jsx    login state
    api.js                   axios client with JWT interceptor
sample_data/               example Excel files for upload testing
```

## Notes / things to harden before production

- `SECRET_KEY` in `app/security.py` is a placeholder — move to an environment variable.
- CORS is wide open (`allow_origins=["*"]`) — restrict to your frontend's origin.
- SQLite is fine for a demo/small team; swap the SQLAlchemy URL in `database.py` for
  Postgres/MySQL for production (SQLAlchemy makes this a one-line change).
- Add password-reset / user self-service flows as needed — the `users` router currently
  only supports admin-created accounts.
